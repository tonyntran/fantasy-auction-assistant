"""
Fantasy Auction Assistant — Local backend server.
Receives draft data from the Chrome extension, runs the calculation engine,
optionally calls Gemini for AI-enhanced advice, and returns results.

Run with: uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import re

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import DraftUpdate, FullAdvice
from config import settings
from state import DraftState
from engine import get_engine_advice
from ai_advisor import get_ai_advice, precompute_advice
from event_store import EventStore
from projections import load_and_merge_projections
from ticker import TickerBuffer, TickerEvent, TickerEventType
from dead_money import process_dead_money_alerts

_start_time = time.time()


# -----------------------------------------------------------------
# Lifespan: load CSV on startup
# -----------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    state = DraftState()

    # Load projections — multi-source if configured, single CSV otherwise
    if settings.csv_paths:
        paths = [p.strip() for p in settings.csv_paths.split(",") if p.strip()]
        weights = None
        if settings.projection_weights:
            weights = [float(w) for w in settings.projection_weights.split(",") if w.strip()]
        merged = load_and_merge_projections(paths, weights)
        state.load_from_merged(merged)
        print(f"  Multi-source: merged {len(paths)} CSVs")
    else:
        state.load_projections(settings.csv_path)

    # Load ADP data if configured
    if settings.adp_csv_path:
        from adp import load_adp_from_csv
        adp_data = load_adp_from_csv(settings.adp_csv_path)
        matched = 0
        for norm_name, adp_val in adp_data.items():
            player = state.get_player(norm_name)
            if player:
                player.adp_value = adp_val
                matched += 1
        print(f"  ADP loaded: {matched}/{len(adp_data)} players matched")

    # Open event store and replay any existing events for crash recovery
    event_store = EventStore()
    event_store.open(settings.event_log_path)
    events = event_store.replay()
    replayed = 0
    if events:
        print(f"  Replaying {len(events)} events from log...")
        for event in events:
            if event["type"] == "draft_update":
                try:
                    update = DraftUpdate(**event["payload"])
                    state.update_from_draft_event(update)
                    replayed += 1
                except Exception as e:
                    print(f"  WARNING: Skip replay event #{event.get('seq')}: {e}")
            elif event["type"] == "manual":
                cmd = event["payload"].get("command", "")
                # Replay sold/budget/undo commands (skip nom which is read-only)
                if cmd and not cmd.lower().startswith("nom "):
                    _replay_manual_command(cmd, state)
                    replayed += 1

    print(f"\n{'='*60}")
    print(f"  Fantasy Auction Assistant")
    print(f"{'='*60}")
    print(f"  Sport:           {settings.sport_name}")
    print(f"  Roster slots:    {settings.roster_slots}")
    print(f"  Players loaded:  {len(state.players)}")
    drafted = sum(1 for ps in state.players.values() if ps.is_drafted)
    if replayed:
        print(f"  Events replayed: {replayed} ({drafted} players drafted)")
    print(f"  My team:         {settings.my_team_name}")
    print(f"  Budget:          ${settings.budget}")
    print(f"  League size:     {settings.league_size}")
    print(f"  Inflation:       {state.get_inflation_factor():.3f}")
    ai_status = "configured" if settings.gemini_api_key and not settings.gemini_api_key.startswith("your-") else "not configured (engine-only mode)"
    print(f"  Gemini AI:       {ai_status}")
    print(f"{'='*60}\n")
    yield
    event_store.close()


def _replay_manual_command(cmd: str, state: DraftState):
    """Replay a manual command during event log recovery (no logging, no event store writes)."""
    import re as _re

    undo_match = _re.match(r"^undo\s+(.+)$", cmd, _re.IGNORECASE)
    if undo_match:
        player_name = undo_match.group(1).strip()
        player = state.get_player(player_name)
        if player and player.is_drafted:
            player.is_drafted = False
            player.draft_price = None
            player.drafted_by_team = None
            for slot, occupant in state.my_team.roster.items():
                if occupant and occupant.lower() == player.projection.player_name.lower():
                    state.my_team.roster[slot] = None
            state.my_team.players_acquired = [
                p for p in state.my_team.players_acquired
                if p["name"].lower() != player.projection.player_name.lower()
            ]
            state._recompute_aggregates()
        return

    budget_match = _re.match(r"^budget\s+(\d+)$", cmd, _re.IGNORECASE)
    if budget_match:
        new_budget = int(budget_match.group(1))
        state.my_team.budget = new_budget
        for key in state.team_budgets:
            if key.lower().strip() == settings.my_team_name.lower().strip():
                state.team_budgets[key] = new_budget
        state._recompute_aggregates()
        return

    sold_match = _re.match(r"^(.+?)\s+(\d+)(?:\s+(\d+))?\s*$", cmd)
    if sold_match:
        player_name = sold_match.group(1).strip()
        price = int(sold_match.group(2))
        team_id = sold_match.group(3)
        player = state.get_player(player_name)
        if player and not player.is_drafted:
            player.is_drafted = True
            player.draft_price = price
            player.drafted_by_team = f"Team #{team_id}" if team_id else "Unknown Team"
            state._recompute_aggregates()


app = FastAPI(title="Fantasy Auction Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------
# WebSocket clients
# -----------------------------------------------------------------

ws_clients: list[WebSocket] = []


# -----------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------

@app.post("/draft_update")
async def draft_update(data: DraftUpdate):
    """
    Receives draft data from the Chrome extension.
    Updates state, computes engine advice, fires off async AI pre-computation,
    and returns advice in the format the extension expects.
    """
    state = DraftState()
    ticker = TickerBuffer()

    # Auto-detect sport from extension payload (if SPORT=auto)
    if data.sport and state.resolved_sport == "auto":
        state.resolve_sport(data.sport)

    # Capture pre-sale inflation for dead money FMV calculation
    pre_sale_inflation = state.get_inflation_factor()

    # Process ticker events (nominations + bids) before state update
    ticker.process_update(data)

    state.update_from_draft_event(data)

    # Process newly drafted players for ticker + dead money
    for ps in state.newly_drafted:
        from engine import calculate_fmv
        fmv = calculate_fmv(ps, state)
        team = ps.drafted_by_team or "Unknown"
        ticker.push(TickerEvent(
            event_type=TickerEventType.PLAYER_SOLD,
            timestamp=time.time(),
            message=f"{ps.projection.player_name} sold to {team} for ${ps.draft_price} (FMV ${round(fmv, 1)})",
            player_name=ps.projection.player_name,
            team_name=team,
            amount=float(ps.draft_price) if ps.draft_price else 0,
        ))

    # Budget alerts — teams running low
    for team in data.teams:
        if team.remainingBudget is not None and team.rosterSize is not None:
            empty_slots = max(0, settings.roster_size - (team.rosterSize or 0))
            if empty_slots > 0 and team.remainingBudget <= empty_slots + 2:
                ticker.push(TickerEvent(
                    event_type=TickerEventType.BUDGET_ALERT,
                    timestamp=time.time(),
                    message=f"BUDGET ALERT: {team.name} has ${team.remainingBudget} for {empty_slots} slots",
                    team_name=team.name,
                    amount=float(team.remainingBudget),
                ))

    # Dead money detection
    dead_money_alerts = process_dead_money_alerts(
        state.newly_drafted, state, pre_sale_inflation
    )
    state.dead_money_log.extend(dead_money_alerts)

    # Persist event for crash recovery
    EventStore().append("draft_update", data.model_dump())

    # Terminal logging
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] Draft Update")

    player_name: Optional[str] = None
    current_bid: float = 0

    if data.currentNomination:
        player_name = data.currentNomination.playerName
        current_bid = data.currentBid or 0
        print(f"  Player: {player_name}  |  Bid: ${int(current_bid)}  |  Inflation: {state.get_inflation_factor():.3f}")
    elif data.teams:
        print(f"  No active nomination  |  Teams: {len(data.teams)}  |  Picks: {len(data.draftLog)}")

    # Compute engine advice (fast, synchronous, pure math)
    advice_html = "Waiting for a nomination..."
    response = {
        "advice": advice_html,
        "status": "ok",
        "tickerEvents": ticker.get_recent(10),
        "deadMoneyAlerts": dead_money_alerts,
    }

    if player_name:
        engine_advice = get_engine_advice(player_name, current_bid, state)

        # Fire-and-forget AI pre-computation (won't block response)
        asyncio.create_task(precompute_advice(player_name, current_bid, state))

        # Build HTML for the overlay
        advice_html = _format_advice_html(player_name, current_bid, engine_advice)
        print(f"  >> {engine_advice.action.value}: max ${engine_advice.max_bid}, FMV ${engine_advice.fmv}")

        # Build top remaining for overlay
        from engine import calculate_fmv
        top_remaining = {}
        for pos in settings.display_positions:
            remaining = state.get_remaining_players(pos)[:3]
            top_remaining[pos] = [
                {"name": p.projection.player_name, "fmv": round(calculate_fmv(p, state), 1)}
                for p in remaining
            ]

        response = {
            "advice": advice_html,
            "status": "ok",
            "suggestedBid": engine_advice.max_bid,
            "playerValue": engine_advice.fmv,
            # Extra data for enhanced overlay
            "myRoster": {slot: occupant for slot, occupant in state.my_team.roster.items()},
            "rosterSummary": f"{len(state.my_team.players_acquired)}/{settings.roster_size}",
            "topRemaining": top_remaining,
            "vona": engine_advice.vona,
            "vonaNextPlayer": engine_advice.vona_next_player,
            "tickerEvents": ticker.get_recent(10),
            "deadMoneyAlerts": dead_money_alerts,
        }

        # Broadcast full snapshot to WebSocket dashboard clients
        await _broadcast_ws({
            "type": "state_snapshot",
            "data": _get_dashboard_snapshot(state),
        })

    return response


@app.get("/advice")
async def get_advice(player: str = Query(..., description="Player name")):
    """
    Returns AI-enhanced advice (cached) or computes on the fly.
    Use this for on-demand lookups from a custom UI.
    """
    state = DraftState()
    current_bid: float = 0

    # Use current bid from latest state if this is the nominated player
    raw_nom = state.raw_latest.get("currentNomination")
    if raw_nom and isinstance(raw_nom, dict):
        if raw_nom.get("playerName", "").lower() == player.lower():
            current_bid = state.raw_latest.get("currentBid") or 0

    engine_advice = get_engine_advice(player, current_bid, state)
    full_advice = await get_ai_advice(player, current_bid, state, engine_advice)

    return full_advice.model_dump()


# -----------------------------------------------------------------
# Manual Override ("Panic" Mode)
# -----------------------------------------------------------------

class ManualInput(BaseModel):
    command: str  # e.g. "Bijan 55", "sold Bijan 55 3", "budget 180", "undo Bijan"


@app.post("/manual")
async def manual_override(data: ManualInput):
    """
    Manual override for when the scraper fails or you need to correct state.

    Supported commands:
      "PlayerName Price"             — Mark player as sold for $Price (unknown team)
      "PlayerName Price TeamId"      — Mark player as sold for $Price to team #TeamId
      "budget 180"                   — Manually set your remaining budget
      "undo PlayerName"              — Un-draft a player (reverse a mistake)
      "nom PlayerName"               — Get advice for a player without a live bid
      "nom PlayerName Price"         — Get advice for a player at a specific bid
    """
    state = DraftState()
    cmd = data.command.strip()
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] Manual Override: \"{cmd}\"")

    # --- UNDO: "undo PlayerName" ---
    undo_match = re.match(r"^undo\s+(.+)$", cmd, re.IGNORECASE)
    if undo_match:
        player_name = undo_match.group(1).strip()
        player = state.get_player(player_name)
        if player and player.is_drafted:
            player.is_drafted = False
            player.draft_price = None
            player.drafted_by_team = None
            # Remove from my roster if present
            for slot, occupant in state.my_team.roster.items():
                if occupant and occupant.lower() == player.projection.player_name.lower():
                    state.my_team.roster[slot] = None
            state.my_team.players_acquired = [
                p for p in state.my_team.players_acquired
                if p["name"].lower() != player.projection.player_name.lower()
            ]
            state._recompute_aggregates()
            EventStore().append("manual", {"command": cmd})
            print(f"  Undrafted: {player.projection.player_name}")
            return {
                "status": "ok",
                "action": "undo",
                "advice": f'<b style="color:#2196f3">UNDO</b> — {player.projection.player_name} returned to player pool.',
                "player": player.projection.player_name,
            }
        return {
            "status": "error",
            "advice": f'<b style="color:#ff1744">ERROR</b> — "{player_name}" not found or not drafted.',
        }

    # --- BUDGET: "budget 180" ---
    budget_match = re.match(r"^budget\s+(\d+)$", cmd, re.IGNORECASE)
    if budget_match:
        new_budget = int(budget_match.group(1))
        old_budget = state.my_team.budget
        state.my_team.budget = new_budget
        # Also update in team_budgets if tracked
        for key in state.team_budgets:
            if key.lower().strip() == settings.my_team_name.lower().strip():
                state.team_budgets[key] = new_budget
        state._recompute_aggregates()
        EventStore().append("manual", {"command": cmd})
        print(f"  Budget: ${old_budget} -> ${new_budget}")
        return {
            "status": "ok",
            "action": "budget",
            "advice": f'<b style="color:#2196f3">BUDGET</b> — Updated: ${old_budget} → ${new_budget}.',
        }

    # --- SUGGEST: "suggest" — nomination suggestions ---
    if cmd.lower().strip() == "suggest":
        from nomination import get_nomination_suggestions
        suggestions = get_nomination_suggestions(state, top_n=5)
        if not suggestions:
            return {"status": "ok", "advice": '<b style="color:#aaa">No nomination suggestions available.</b>'}
        lines = ['<b style="color:#2196f3">NOMINATION SUGGESTIONS</b><br>']
        for i, s in enumerate(suggestions, 1):
            color = {"BUDGET_DRAIN": "#ff9800", "RIVAL_DESPERATION": "#f44336", "BARGAIN_SNAG": "#4caf50"}.get(s["strategy"], "#aaa")
            lines.append(
                f'{i}. <span style="color:{color}">[{s["strategy"]}]</span> '
                f'<b>{s["player_name"]}</b> ({s["position"]}) — FMV ${s["fmv"]}<br>'
                f'<span style="font-size:11px;color:#aaa">{s["reasoning"]}</span>'
            )
        return {"status": "ok", "action": "suggest", "advice": "<br>".join(lines)}

    # --- WHATIF: "whatif PlayerName Price" ---
    whatif_match = re.match(r"^whatif\s+(.+?)\s+(\d+)\s*$", cmd, re.IGNORECASE)
    if whatif_match:
        from what_if import simulate_what_if
        player_name = whatif_match.group(1).strip()
        price = int(whatif_match.group(2))
        result = simulate_what_if(player_name, price, state)
        if "error" in result:
            return {"status": "error", "advice": f'<b style="color:#ff1744">ERROR</b> — {result["error"]}'}
        lines = [f'<b style="color:#9c27b0">WHAT IF</b> — {player_name} for ${price}<br>']
        lines.append(f'Remaining budget: <b>${result["remaining_budget_after"]}</b>')
        lines.append(f'Roster: {result["roster_completeness"]}<br>')
        if result.get("optimal_remaining_picks"):
            lines.append('<b>Optimal remaining picks:</b>')
            for pick in result["optimal_remaining_picks"][:5]:
                lines.append(f'  {pick["player"]} ({pick["position"]}) ~${pick["estimated_price"]}')
        lines.append(f'<br>Projected total: <b>{result["projected_total_points"]} pts</b>')
        return {"status": "ok", "action": "whatif", "advice": "<br>".join(lines)}

    # --- NOM: "nom PlayerName" or "nom PlayerName Price" ---
    nom_match = re.match(r"^nom\s+(.+?)(?:\s+(\d+))?\s*$", cmd, re.IGNORECASE)
    if nom_match:
        player_name = nom_match.group(1).strip()
        bid = float(nom_match.group(2)) if nom_match.group(2) else 0
        engine_advice = get_engine_advice(player_name, bid, state)
        advice_html = _format_advice_html(player_name, bid, engine_advice)
        print(f"  Nom lookup: {player_name} @ ${int(bid)} -> {engine_advice.action.value}")
        return {
            "status": "ok",
            "action": "nom",
            "advice": advice_html,
            "suggestedBid": engine_advice.max_bid,
            "playerValue": engine_advice.fmv,
        }

    # --- SOLD: "PlayerName Price" or "PlayerName Price TeamId" ---
    sold_match = re.match(r"^(.+?)\s+(\d+)(?:\s+(\d+))?\s*$", cmd)
    if sold_match:
        player_name = sold_match.group(1).strip()
        price = int(sold_match.group(2))
        team_id = sold_match.group(3)

        player = state.get_player(player_name)
        if player is None:
            return {
                "status": "error",
                "advice": f'<b style="color:#ff1744">ERROR</b> — "{player_name}" not found in projections.',
            }

        if player.is_drafted:
            return {
                "status": "error",
                "advice": f'<b style="color:#ff1744">ERROR</b> — {player.projection.player_name} already drafted for ${player.draft_price}. Use "undo {player_name}" first.',
            }

        player.is_drafted = True
        player.draft_price = price
        team_label = f"Team #{team_id}" if team_id else "Unknown Team"
        player.drafted_by_team = team_label
        state._recompute_aggregates()
        EventStore().append("manual", {"command": cmd})

        print(f"  Sold: {player.projection.player_name} for ${price} to {team_label}")
        return {
            "status": "ok",
            "action": "sold",
            "advice": (
                f'<b style="color:#2196f3">MANUAL</b> — '
                f'{player.projection.player_name} sold for <b>${price}</b> to {team_label}. '
                f'Inflation now {state.get_inflation_factor():.3f}.'
            ),
            "player": player.projection.player_name,
            "price": price,
        }

    return {
        "status": "error",
        "advice": (
            '<b style="color:#ff1744">ERROR</b> — Unrecognized command.<br>'
            '<span style="font-size:11px;color:#aaa">'
            'Try: "Bijan 55", "budget 180", "undo Bijan", "nom CeeDee 30"'
            '</span>'
        ),
    }


@app.get("/health")
async def health_check():
    """Heartbeat endpoint for the extension's 5-second health polling."""
    state = DraftState()
    drafted = sum(1 for ps in state.players.values() if ps.is_drafted)
    return {
        "status": "ok",
        "uptime": round(time.time() - _start_time, 1),
        "drafted_count": drafted,
        "inflation": round(state.get_inflation_factor(), 3),
    }


@app.get("/opponents")
async def get_opponents():
    """View opponent positional needs and threat levels."""
    state = DraftState()
    return state.opponent_tracker.get_summary()


@app.get("/sleepers")
async def get_sleepers():
    """End-of-draft bargain targets — players likely to go for $1-3."""
    from sleeper_watch import get_sleeper_candidates
    state = DraftState()
    return {"sleepers": get_sleeper_candidates(state)}


@app.get("/nominate")
async def get_nominations():
    """Nomination strategy suggestions for when it's your turn to nominate."""
    from nomination import get_nomination_suggestions
    state = DraftState()
    return {"suggestions": get_nomination_suggestions(state)}


@app.get("/stream/{player}")
async def stream_advice(player: str, bid: float = 0):
    """Stream AI advice as Server-Sent Events."""
    from sse_starlette.sse import EventSourceResponse
    from ai_advisor import stream_ai_advice

    async def event_generator():
        state = DraftState()
        engine_advice = get_engine_advice(player, bid, state)

        # First event: engine advice (instant)
        yield {"event": "engine", "data": json.dumps(engine_advice.model_dump(), default=str)}

        # Stream AI reasoning
        async for chunk in stream_ai_advice(player, bid, state, engine_advice):
            yield {"event": "ai_chunk", "data": chunk}

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


@app.get("/whatif")
async def whatif(player: str = Query(...), price: int = Query(...)):
    """What-if simulation: what happens if I spend $X on this player?"""
    from what_if import simulate_what_if
    state = DraftState()
    return simulate_what_if(player, price, state)


@app.get("/grade")
async def grade():
    """Post-draft team grade and analysis."""
    from grader import build_grade_prompt
    from ai_advisor import get_draft_grade
    state = DraftState()
    prompt = build_grade_prompt(state)
    result = await get_draft_grade(prompt)
    if result:
        return result
    # Fallback: engine-only grade
    return _build_engine_grade(state)


@app.get("/dashboard/state")
async def dashboard_state():
    """Full state snapshot for the web dashboard."""
    from sleeper_watch import get_sleeper_candidates
    from nomination import get_nomination_suggestions
    state = DraftState()
    return _get_dashboard_snapshot(state)


@app.get("/state")
async def get_state():
    """View the current draft state summary."""
    state = DraftState()
    return state.get_state_summary()


@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "Fantasy Auction Assistant backend is live.",
        "my_team": settings.my_team_name,
        "league_size": settings.league_size,
        "budget": settings.budget,
        "endpoints": {
            "POST /draft_update": "Receives draft data from the extension",
            "POST /manual": "Manual override (sold, budget, undo, nom, suggest, whatif)",
            "GET /advice?player=<name>": "Get AI-enhanced advice for a specific player",
            "GET /health": "Heartbeat / uptime check",
            "GET /state": "View current draft state summary",
            "GET /opponents": "Opponent positional needs",
            "GET /sleepers": "End-of-draft bargain targets",
            "GET /nominate": "Nomination strategy suggestions",
            "GET /whatif?player=<name>&price=<int>": "What-if draft simulation",
            "GET /grade": "Post-draft team grade",
            "GET /stream/{player}?bid={bid}": "SSE streaming AI advice",
            "GET /dashboard/state": "Full dashboard state snapshot",
            "WS /ws": "WebSocket for real-time updates",
        },
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket for future real-time UIs. Accepts draft updates and broadcasts advice."""
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            data = await ws.receive_json()
            if "currentNomination" in data:
                update = DraftUpdate(**data)
                state = DraftState()
                state.update_from_draft_event(update)
    except WebSocketDisconnect:
        ws_clients.remove(ws)


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _format_advice_html(player_name: str, current_bid: float, advice) -> str:
    """Format advice as color-coded HTML for the extension overlay."""
    color_map = {
        "BUY": "#00c853",
        "PASS": "#ff1744",
        "PRICE_ENFORCE": "#ffab00",
        "NOMINATE": "#2196f3",
    }
    action = advice.action.value if hasattr(advice.action, "value") else advice.action
    color = color_map.get(action, "#e0e0e0")

    lines = [
        f'<b style="color:{color};font-size:15px">{action}</b> — <b>{player_name}</b>',
        f'FMV: <b>${advice.fmv}</b> &nbsp;|&nbsp; Bid up to: <b style="color:{color}">${advice.max_bid}</b>',
        f'Inflation: {advice.inflation_rate:.2f}x &nbsp;|&nbsp; Scarcity: {advice.scarcity_multiplier:.2f}x &nbsp;|&nbsp; VORP: {advice.vorp:.1f} &nbsp;|&nbsp; VONA: {advice.vona:.1f}',
        f'<span style="font-size:11px;color:#aaa;margin-top:4px;display:block">{advice.reasoning}</span>',
    ]
    if advice.vona_next_player:
        lines.insert(3, f'<span style="font-size:11px;color:#8899aa">Next at pos: {advice.vona_next_player}</span>')
    return "<br>".join(lines)


async def _broadcast_ws(message: dict):
    """Send a message to all connected WebSocket clients."""
    disconnected = []
    for ws in ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ws_clients.remove(ws)


def _get_dashboard_snapshot(state: DraftState) -> dict:
    """Build a comprehensive state snapshot for the web dashboard."""
    from sleeper_watch import get_sleeper_candidates
    from nomination import get_nomination_suggestions
    from engine import calculate_fmv

    # All players with status
    players = []
    for key, ps in state.players.items():
        players.append({
            "name": ps.projection.player_name,
            "position": ps.projection.position.value,
            "tier": ps.projection.tier,
            "projected_points": ps.projection.projected_points,
            "baseline_aav": ps.projection.baseline_aav,
            "fmv": round(calculate_fmv(ps, state), 1),
            "vorp": round(ps.vorp, 1),
            "is_drafted": ps.is_drafted,
            "draft_price": ps.draft_price,
            "drafted_by": ps.drafted_by_team,
            "adp_value": ps.adp_value,
            "vona": round(ps.vona, 1),
            "vona_next_player": ps.vona_next_player,
        })

    # Top remaining by position
    top_remaining = {}
    for pos in settings.display_positions:
        remaining = state.get_remaining_players(pos)[:3]
        top_remaining[pos] = [
            {"name": p.projection.player_name, "fmv": round(calculate_fmv(p, state), 1), "vorp": round(p.vorp, 1)}
            for p in remaining
        ]

    return {
        "players": players,
        "my_team": state.my_team.model_dump(),
        "budgets": state.team_budgets,
        "inflation": round(state.get_inflation_factor(), 3),
        "inflation_history": state.inflation_history,
        "draft_log": state.draft_log,
        "positional_need": state.get_positional_need(),
        "sleepers": get_sleeper_candidates(state),
        "nominations": get_nomination_suggestions(state),
        "opponent_needs": state.opponent_tracker.get_summary(),
        "top_remaining": top_remaining,
        "ticker_events": TickerBuffer().get_recent(20),
        "dead_money_alerts": state.dead_money_log,
        "sport": settings.sport,
        "positions": settings.positions,
        "display_positions": settings.display_positions,
        "position_badges": settings.sport_profile.get("position_badges", {}),
    }


def _build_engine_grade(state: DraftState) -> dict:
    """Fallback grade when AI is unavailable."""
    my = state.my_team
    total_spent = my.total_budget - my.budget
    picks = my.players_acquired
    total_points = sum(
        state.get_player(p["name"]).projection.projected_points
        for p in picks
        if state.get_player(p["name"])
    )
    total_surplus = sum(
        state.get_player(p["name"]).projection.baseline_aav - p["price"]
        for p in picks
        if state.get_player(p["name"])
    )
    return {
        "overall_grade": "N/A (AI unavailable)",
        "total_spent": total_spent,
        "total_projected_points": round(total_points, 1),
        "total_surplus_value": round(total_surplus, 1),
        "picks": picks,
        "source": "engine",
    }
