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

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import DraftUpdate, FullAdvice
from config import settings, DRAFT_STRATEGIES
from state import DraftState
from engine import get_engine_advice
from ai_advisor import get_ai_advice, precompute_advice, ai_status as _ai_status_ref, close_http_client
import ai_advisor as _ai_advisor_mod
from event_store import EventStore
from projections import load_and_merge_projections
from ticker import TickerBuffer, TickerEvent, TickerEventType

import player_news
import draft_plan

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
        state.active_sheet = "merged"
        print(f"  Multi-source: merged {len(paths)} CSVs")
    else:
        state.load_projections(settings.csv_path)
        # active_sheet is set inside load_projections via path.stem

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

    # Load keepers (must happen AFTER projections, BEFORE event replay)
    from keepers import load_keepers
    keepers = load_keepers(state)
    if keepers:
        print(f"  [Keepers] Loaded {len(keepers)} keeper(s)")

    # Load player news/injury data from Sleeper API
    await player_news.ensure_loaded()

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
    print(f"  Platform:        {settings.platform}")
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
    from ai_advisor import _has_ai_key
    provider = settings.ai_provider.lower()
    if _has_ai_key():
        model = settings.claude_model if provider == "claude" else settings.gemini_model
        ai_display = f"{provider} ({model})"
    else:
        ai_display = "not configured (engine-only mode)"
    print(f"  AI Provider:     {ai_display}")
    print(f"{'='*60}\n")
    yield
    await close_http_client()
    event_store.close()


def _replay_manual_command(cmd: str, state: DraftState):
    """Replay a manual command during event log recovery (no logging, no event store writes)."""
    undo_match = re.match(r"^undo\s+(.+)$", cmd, re.IGNORECASE)
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

    budget_match = re.match(r"^budget\s+(\d+)$", cmd, re.IGNORECASE)
    if budget_match:
        new_budget = int(budget_match.group(1))
        state.my_team.budget = new_budget
        for key in state.team_budgets:
            if key.lower().strip() == settings.my_team_name.lower().strip():
                state.team_budgets[key] = new_budget
        state._recompute_aggregates()
        return

    sold_match = re.match(r"^(.+?)\s+(\d+)(?:\s+(\d+))?\s*$", cmd)
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

    # Auto-detect platform from extension payload
    if data.platform and data.platform.lower() in ("espn", "sleeper"):
        settings.platform = data.platform.lower()

    # Auto-detect sport from extension payload (if SPORT=auto)
    if data.sport and state.resolved_sport == "auto":
        state.resolve_sport(data.sport)

    # Process ticker events (nominations + bids) before state update
    ticker.process_update(data)

    state.update_from_draft_event(data)

    # Process newly drafted players for ticker
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

    # Invalidate draft plan cache when players are drafted
    if state.newly_drafted:
        draft_plan.invalidate_plan()

    # Persist event for crash recovery
    EventStore().append("draft_update", data.model_dump())

    # Terminal logging
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] Draft Update ({settings.platform})")

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
        "strategyLabel": settings.active_strategy["label"],
    }

    if player_name:
        engine_advice = get_engine_advice(player_name, current_bid, state)

        # Fire-and-forget AI pre-computation — only on NEW nominations
        from ai_advisor import _advice_cache, CACHE_TTL_SECONDS as _AI_TTL
        _ai_key = player_name.lower().strip()
        _ai_cached = _advice_cache.get(_ai_key)
        if not _ai_cached or (time.time() - _ai_cached[1]) >= _AI_TTL:
            asyncio.create_task(precompute_advice(player_name, current_bid, state))

        # Build HTML for the overlay
        advice_html = _format_advice_html(player_name, current_bid, engine_advice)
        print(f"  >> {engine_advice.action.value}: max ${engine_advice.max_bid}, FMV ${engine_advice.fmv}")

        response = {
            "advice": advice_html,
            "status": "ok",
            "suggestedBid": engine_advice.max_bid,
            "playerValue": engine_advice.fmv,
            "vona": engine_advice.vona,
            "vonaNextPlayer": engine_advice.vona_next_player,
            "tickerEvents": ticker.get_recent(10),
            "strategyLabel": settings.active_strategy["label"],
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
            color = {"BUDGET_DRAIN": "#ff9800", "RIVAL_DESPERATION": "#f44336", "POISON_PILL": "#9c27b0", "BARGAIN_SNAG": "#4caf50"}.get(s["strategy"], "#aaa")
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


@app.get("/team_aliases")
async def get_team_aliases():
    """Get current team aliases."""
    state = DraftState()
    return {"aliases": state.team_aliases, "teams": list(state.team_budgets.keys())}


@app.post("/team_aliases")
async def set_team_aliases(request: dict):
    """Set team display aliases. Body: {"Team 1": "Alice", "Team 3": "Me"}"""
    state = DraftState()
    for original, alias in request.items():
        if isinstance(alias, str) and alias.strip():
            state.team_aliases[original] = alias.strip()
            # If the alias matches MY_TEAM_NAME, register the original so _is_my_team works
            existing = [a.strip().lower() for a in settings.my_team_name.split(",")]
            if state._is_my_team(alias) and original.strip().lower() not in existing:
                settings.my_team_name = settings.my_team_name + "," + original
                print(f"  [Alias] Registered '{original}' as my team alias")
    print(f"  [Alias] Team aliases: {state.team_aliases}")
    return {"aliases": state.team_aliases}


@app.post("/strategy")
async def set_strategy(request: dict):
    """Set the active draft strategy profile."""
    strategy = request.get("strategy", "balanced")
    if strategy not in DRAFT_STRATEGIES:
        return {"status": "error", "message": f"Unknown strategy: {strategy}"}
    settings.draft_strategy = strategy
    return {"strategy": strategy, "label": DRAFT_STRATEGIES[strategy]["label"]}


@app.post("/projection-sheet")
async def switch_projection_sheet(body: dict):
    """Switch the active projection sheet and recompute all values."""
    sheet_name = body.get("sheet")
    available = settings.available_sheets

    if sheet_name not in available:
        raise HTTPException(400, f"Unknown sheet: {sheet_name}. Available: {list(available.keys())}")

    path = available[sheet_name]
    state = DraftState()

    # Reload projections from the new sheet, preserving draft progress
    state.reload_projections(path)

    # Broadcast updated snapshot to WebSocket dashboard clients
    snapshot = _get_dashboard_snapshot(state)
    await _broadcast_ws({"type": "state_snapshot", "data": snapshot})

    return {"active_sheet": sheet_name, "player_count": len(state.players)}


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
    """Get advice for a player. Returns cached AI advice or engine-only."""
    state = DraftState()
    engine_advice = get_engine_advice(player, bid, state)
    full_advice = await get_ai_advice(player, bid, state, engine_advice)
    return full_advice.model_dump()


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


@app.get("/export")
async def export_draft_results(format: str = "json"):
    """Export draft results as JSON or CSV."""
    from engine import calculate_fmv
    import io
    import csv as csv_mod
    from starlette.responses import StreamingResponse

    state = DraftState()

    # Build export data from all drafted players
    picks = []
    for key, ps in state.players.items():
        if ps.is_drafted:
            fmv = calculate_fmv(ps, state)
            picks.append({
                "player": ps.projection.player_name,
                "position": ps.projection.position.value,
                "team": ps.drafted_by_team or "Unknown",
                "price": ps.draft_price,
                "fmv": round(fmv, 1),
                "vorp": round(ps.vorp, 1),
                "vom": round(fmv - ps.draft_price, 1) if ps.draft_price else 0,
                "projected_points": round(ps.projection.projected_points, 1),
                "is_keeper": getattr(ps, "is_keeper", False),
            })

    picks.sort(key=lambda p: p["price"], reverse=True)

    my_team_aliases = [a.strip().lower() for a in settings.my_team_name.split(",")]
    my_picks = [p for p in picks if p["team"].lower() in my_team_aliases]
    export = {
        "draft_date": datetime.now().isoformat(),
        "league_size": settings.league_size,
        "budget": settings.budget,
        "platform": settings.platform,
        "my_team": settings.my_team_name,
        "total_picks": len(picks),
        "picks": picks,
        "my_picks": my_picks,
        "summary": {
            "total_spent": sum(p["price"] for p in my_picks),
            "total_projected_points": sum(p["projected_points"] for p in my_picks),
            "total_vom": sum(p["vom"] for p in my_picks),
        },
    }

    if format == "csv":
        output = io.StringIO()
        fieldnames = ["player", "position", "team", "price", "fmv", "vorp", "vom", "projected_points", "is_keeper"]
        writer = csv_mod.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(picks)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=draft_results.csv"},
        )

    # Auto-save to data/historical/ for JSON exports
    _auto_save_historical(export)

    return export


def _auto_save_historical(export: dict):
    """Auto-save draft results for future historical reference."""
    from pathlib import Path

    hist_dir = Path("data/historical")
    hist_dir.mkdir(parents=True, exist_ok=True)

    date_str = export["draft_date"][:10]  # YYYY-MM-DD
    filename = f"draft_{date_str}_{export['platform']}.json"
    filepath = hist_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, default=str)

    print(f"[Export] Draft results saved to {filepath}")


@app.get("/optimize")
async def optimize():
    """Optimal remaining picks given current budget and needs."""
    from roster_optimizer import get_optimal_plan
    state = DraftState()
    return get_optimal_plan(state)


@app.get("/draft-plan")
async def get_draft_plan():
    """On-demand AI draft plan with strategic spending analysis."""
    state = DraftState()
    return await draft_plan.get_ai_draft_plan(state)


@app.get("/dashboard/state")
async def dashboard_state():
    """Full state snapshot for the web dashboard."""
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
            "GET /export?format=json|csv": "Export draft results as JSON or CSV",
            "GET /draft-plan": "On-demand AI draft plan with spending analysis",
            "GET /dashboard/state": "Full dashboard state snapshot",
            "WS /ws": "WebSocket for real-time updates",
        },
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Subscription-only WebSocket for real-time dashboard updates.

    This handler is read-only: it pushes snapshots to clients via
    _broadcast_ws() but does NOT accept or process incoming mutations.
    State changes arrive through the HTTP POST /draft_update endpoint.
    """
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            # Keep the connection alive; incoming messages are ignored.
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in ws_clients:
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


def _build_player_list(state: DraftState) -> list[dict]:
    """Build the list of all players with FMV, VORP, VONA, tier, and draft status."""
    from engine import calculate_fmv

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
            "is_keeper": ps.is_keeper,
            "draft_price": ps.draft_price,
            "drafted_by": state.apply_alias(ps.drafted_by_team),
            "adp_value": ps.adp_value,
            "vona": round(ps.vona, 1),
            "vona_next_player": ps.vona_next_player,
        })
    return players


def _build_top_remaining(state: DraftState) -> dict[str, list[dict]]:
    """Build the top 5 undrafted players per position with tier-break flags."""
    from engine import calculate_fmv

    top_remaining = {}
    for pos in settings.display_positions:
        remaining = state.get_remaining_players(pos)[:5]
        entries = []
        for i, p in enumerate(remaining):
            drop_off = None
            if i < len(remaining) - 1:
                drop_off = round(p.projection.projected_points - remaining[i + 1].projection.projected_points, 1)
            entries.append({
                "name": p.projection.player_name,
                "fmv": round(calculate_fmv(p, state), 1),
                "vorp": round(p.vorp, 1),
                "pts_per_game": round(p.projection.projected_points / settings.season_games, 1),
                "drop_off": drop_off,
            })
        # Flag tier breaks: drop-off > 1.5x the average gap in this group
        gaps = [e["drop_off"] for e in entries if e["drop_off"] is not None and e["drop_off"] > 0]
        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        for e in entries:
            e["tier_break"] = e["drop_off"] is not None and avg_gap > 0 and e["drop_off"] > avg_gap * 1.5
        top_remaining[pos] = entries
    return top_remaining


def _build_ticker_events(state: DraftState) -> list[dict]:
    """Get recent ticker events with team aliases applied."""
    ticker_events = TickerBuffer().get_recent(20)
    for evt in ticker_events:
        if evt.get("team_name"):
            evt["team_name"] = state.apply_alias(evt["team_name"])
        if evt.get("message"):
            for orig, alias in state.team_aliases.items():
                evt["message"] = evt["message"].replace(orig, alias)
    return ticker_events


def _build_current_advice(state: DraftState) -> Optional[dict]:
    """Build advice dict for the currently nominated player, merging engine and cached AI."""
    from engine import get_engine_advice

    raw_nom = state.raw_latest.get("currentNomination")
    if not (raw_nom and isinstance(raw_nom, dict) and raw_nom.get("playerName")):
        return None

    nom_player = raw_nom["playerName"]
    nom_bid = state.raw_latest.get("currentBid") or 0
    nom_bidder = state.raw_latest.get("highBidder")
    try:
        engine_advice = get_engine_advice(nom_player, nom_bid, state)

        # Player news for nominated player
        nom_news = player_news.get_player_status(nom_player)

        # Look up the player object for extra fields
        nom_player_obj = state.get_player(nom_player)
        nom_pos = nom_player_obj.projection.position.value if nom_player_obj else None

        # Base advice from engine (always present)
        current_advice = {
            "player": nom_player,
            "current_bid": nom_bid,
            "high_bidder": state.apply_alias(str(nom_bidder)) if nom_bidder else None,
            "action": engine_advice.action.value,
            "max_bid": engine_advice.max_bid,
            "fmv": engine_advice.fmv,
            "base_fmv": engine_advice.base_fmv,
            "baseline_aav": nom_player_obj.projection.baseline_aav if nom_player_obj else None,
            "inflation_rate": round(state.get_inflation_factor(), 3),
            "engine_reasoning": engine_advice.reasoning,
            "ai_reasoning": None,
            "reasoning": engine_advice.reasoning,
            "vona": engine_advice.vona,
            "vona_next_player": engine_advice.vona_next_player,
            "scarcity_multiplier": engine_advice.scarcity_multiplier,
            "strategy_multiplier": engine_advice.strategy_multiplier,
            "vorp": engine_advice.vorp,
            "vorp_per_game": round(engine_advice.vorp / settings.season_games, 1) if engine_advice.vorp else 0,
            "vorp_replacement_player": state.replacement_player.get(nom_pos) if nom_pos else None,
            "vona_per_game": round(engine_advice.vona / settings.season_games, 1) if engine_advice.vona else 0,
            "surplus_value": round(engine_advice.fmv - nom_bid, 1) if nom_bid > 0 and engine_advice.fmv else None,
            "adp_vs_fmv": engine_advice.adp_vs_fmv,
            "opponent_demand": engine_advice.opponent_demand,
            "source": "engine",
            "player_news": nom_news,
        }

        # Overlay AI advice if cached
        from ai_advisor import _advice_cache, CACHE_TTL_SECONDS
        cache_key = nom_player.lower().strip()
        ai_cached = _advice_cache.get(cache_key)
        if ai_cached and (time.time() - ai_cached[1]) < CACHE_TTL_SECONDS:
            ai = ai_cached[0]
            current_advice["action"] = ai.action.value
            current_advice["max_bid"] = ai.max_bid
            current_advice["ai_reasoning"] = ai.reasoning
            current_advice["reasoning"] = ai.reasoning
            current_advice["source"] = ai.source
        return current_advice
    except Exception:
        return None


def _build_opponent_needs(state: DraftState) -> dict:
    """Build opponent positional needs with team aliases applied."""
    opponent_needs = state.opponent_tracker.get_summary()
    # Build aliased name->team_id mapping so frontend can correlate budget names to roster data
    name_to_id = {}
    for tid, tname in opponent_needs.get("team_names", {}).items():
        aliased = state.apply_alias(tname)
        name_to_id[aliased] = tid
    opponent_needs["name_to_id"] = name_to_id
    # Set display_name on each threat entry
    for t in opponent_needs.get("threat_levels", []):
        tid = str(t.get("team_id", ""))
        raw_name = opponent_needs.get("team_names", {}).get(tid, tid)
        t["display_name"] = state.apply_alias(raw_name)
    return opponent_needs


def _build_vom_leaderboard(state: DraftState) -> list[dict]:
    """Build the Value Over Market leaderboard for all drafted players, sorted by VOM."""
    from engine import calculate_fmv

    vom_leaderboard = []
    for ps in state.players.values():
        if ps.is_drafted and ps.draft_price is not None:
            fmv = calculate_fmv(ps, state)
            vom = round(fmv - ps.draft_price, 1)
            par_dollar = round(ps.vorp / ps.draft_price, 2) if ps.draft_price > 0 else None
            vom_leaderboard.append({
                "player_name": ps.projection.player_name,
                "position": ps.projection.position.value,
                "draft_price": ps.draft_price,
                "fmv": round(fmv, 1),
                "vom": vom,
                "par_dollar": par_dollar,
                "drafted_by": state.apply_alias(ps.drafted_by_team),
            })
    vom_leaderboard.sort(key=lambda x: x["vom"], reverse=True)
    return vom_leaderboard


def _build_positional_prices(state: DraftState) -> dict[str, dict]:
    """Compute actual price vs FMV percentage per position for all drafted players."""
    from engine import calculate_fmv

    pos_price_data: dict[str, dict] = {}
    for ps in state.players.values():
        if ps.is_drafted and ps.draft_price is not None:
            pos = ps.projection.position.value
            if pos not in pos_price_data:
                pos_price_data[pos] = {"total_paid": 0, "total_fmv": 0, "count": 0}
            pos_price_data[pos]["total_paid"] += ps.draft_price
            pos_price_data[pos]["total_fmv"] += calculate_fmv(ps, state)
            pos_price_data[pos]["count"] += 1
    positional_prices = {}
    for pos in settings.display_positions:
        d = pos_price_data.get(pos)
        if d and d["total_fmv"] > 0:
            pct = round(d["total_paid"] / d["total_fmv"] * 100)
            positional_prices[pos] = {"pct_of_fmv": pct, "count": d["count"]}
        else:
            positional_prices[pos] = {"pct_of_fmv": 100, "count": 0}
    return positional_prices


def _build_positional_run(state: DraftState, positional_prices: dict[str, dict]) -> Optional[dict]:
    """Detect positional runs: 3+ consecutive same-position sales in the recent draft log."""
    from engine import calculate_fmv

    if len(state.draft_log) < 3:
        return None

    # Walk backwards through draft log to find runs
    run_pos = None
    run_count = 0
    run_above_fmv = 0
    for entry in reversed(state.draft_log[-6:]):
        name = entry.get("playerName", "")
        ps = state.get_player(name)
        if not ps:
            break
        pos = ps.projection.position.value
        price = entry.get("bidAmount", 0)
        if run_pos is None:
            run_pos = pos
            run_count = 1
            if price > calculate_fmv(ps, state):
                run_above_fmv = 1
        elif pos == run_pos:
            run_count += 1
            if price > calculate_fmv(ps, state):
                run_above_fmv += 1
        else:
            break
    if run_count >= 3:
        avg_pct = positional_prices.get(run_pos, {}).get("pct_of_fmv", 100)
        return {
            "position": run_pos,
            "consecutive": run_count,
            "above_fmv_count": run_above_fmv,
            "avg_pct_of_fmv": avg_pct,
        }
    return None


def _build_money_velocity(state: DraftState) -> dict:
    """Compute league-wide spending velocity metrics."""
    total_drafted = sum(1 for ps in state.players.values() if ps.is_drafted)
    total_players = len(state.players)
    total_spent = sum(
        ps.draft_price for ps in state.players.values()
        if ps.is_drafted and ps.draft_price is not None
    )
    total_league_budget = settings.league_size * settings.budget
    draft_pct = round(total_drafted / total_players * 100, 1) if total_players else 0
    spend_pct = round(total_spent / total_league_budget * 100, 1) if total_league_budget else 0
    # Velocity: if spend_pct > draft_pct, money is flowing fast (expensive early picks)
    # Predict bargain zone: when velocity drops below 1.0
    velocity = round(spend_pct / draft_pct, 2) if draft_pct > 0 else 1.0
    avg_price = round(total_spent / total_drafted, 1) if total_drafted else 0
    return {
        "total_spent": total_spent,
        "total_budget": total_league_budget,
        "spend_pct": spend_pct,
        "draft_pct": draft_pct,
        "velocity": velocity,
        "avg_price": avg_price,
        "players_drafted": total_drafted,
        "players_total": total_players,
    }


def _build_my_team_data(state: DraftState) -> dict:
    """Build augmented my-team data with NFL team and bye week info."""
    my_team_data = state.my_team.model_dump()
    for p in my_team_data.get("players_acquired", []):
        roster_info = player_news.get_player_roster_info(p["name"])
        p["team"] = roster_info.get("team")
        p["bye_week"] = roster_info.get("bye_week")
    return my_team_data


def _build_budgets(state: DraftState) -> dict[str, int]:
    """Get team budgets with aliases applied."""
    return state.get_aliased_budgets()


def _get_dashboard_snapshot(state: DraftState) -> dict:
    """Build a comprehensive state snapshot for the web dashboard.

    Orchestrates sub-functions that each compute one section of the snapshot,
    then assembles and returns the final dict.
    """
    from sleeper_watch import get_sleeper_candidates
    from nomination import get_nomination_suggestions
    from engine import get_positional_vona_summary
    from roster_optimizer import get_optimal_plan

    players = _build_player_list(state)
    top_remaining = _build_top_remaining(state)
    ticker_events = _build_ticker_events(state)
    current_advice = _build_current_advice(state)
    opponent_needs = _build_opponent_needs(state)
    player_news_map = player_news.get_news_for_undrafted(state)
    vom_leaderboard = _build_vom_leaderboard(state)
    optimizer = get_optimal_plan(state)
    positional_prices = _build_positional_prices(state)
    positional_run = _build_positional_run(state, positional_prices)
    money_velocity = _build_money_velocity(state)
    my_team_data = _build_my_team_data(state)
    budgets = _build_budgets(state)

    return {
        "players": players,
        "my_team": my_team_data,
        "budgets": budgets,
        "team_aliases": state.team_aliases,
        "inflation": round(state.get_inflation_factor(), 3),
        "inflation_history": state.inflation_history,
        "draft_log": state.draft_log,
        "positional_need": state.get_positional_need(),
        "sleepers": get_sleeper_candidates(state),
        "nominations": get_nomination_suggestions(state),
        "opponent_needs": opponent_needs,
        "top_remaining": top_remaining,
        "ticker_events": ticker_events,

        "current_advice": current_advice,
        "ai_status": _ai_advisor_mod.ai_status,
        "sport": settings.sport,
        "positions": settings.positions,
        "display_positions": settings.display_positions,
        "position_badges": settings.sport_profile.get("position_badges", {}),
        "vom_leaderboard": vom_leaderboard,
        "positional_vona": get_positional_vona_summary(state),
        "optimizer": optimizer,
        "positional_prices": positional_prices,
        "positional_run": positional_run,
        "money_velocity": money_velocity,
        "player_news": player_news_map,
        "draft_plan_staleness": draft_plan.get_picks_since_plan(state),
        "strategy": settings.draft_strategy,
        "strategy_label": settings.active_strategy["label"],
        "strategies": {
            k: {"label": v["label"], "description": v["description"]}
            for k, v in DRAFT_STRATEGIES.items()
        },
        "available_sheets": list(settings.available_sheets.keys()),
        "active_sheet": state.active_sheet if state.active_sheet else (
            list(settings.available_sheets.keys())[0] if settings.available_sheets else None
        ),
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
