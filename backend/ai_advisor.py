"""
AI advisor module — supports Gemini and Claude for AI-enhanced auction advice.
Falls back to pure engine advice if the AI is slow, unavailable, or misconfigured.

Features:
  - Richer context (opponent model, ADP, recent picks, team synergy)
  - Provider-agnostic: set AI_PROVIDER=gemini or AI_PROVIDER=claude
  - Post-draft grading with extended timeout
"""

import asyncio
import json
import time
from typing import Optional

import httpx

from models import EngineAdvice, FullAdvice, AdviceAction
from state import DraftState
from config import settings
from engine import get_engine_advice


# In-memory cache: player_name_lower -> (FullAdvice, timestamp)
# Keyed only by player name — one AI call per nomination, not per bid change
_advice_cache: dict[str, tuple[FullAdvice, float]] = {}
CACHE_TTL_SECONDS = 120

# Track in-flight requests to avoid duplicate concurrent calls
_inflight: set[str] = set()

# Rate limit backoff — when we hit 429, pause all calls until this time
_rate_limit_until: float = 0.0
_RATE_LIMIT_BACKOFF_SECONDS = 60  # wait 60s after a 429

# Last AI status for surfacing on the dashboard
ai_status: str = "idle"  # "idle" | "ok" | "rate_limited" | "error: ..." | "no_key"


def _build_strategy_context(player_tier: int = 0) -> str:
    """Build a strategy description for the AI prompt.
    When Studs & Steals is active, injects tier-specific guidance."""
    strategy = settings.active_strategy
    if settings.draft_strategy == "balanced":
        return ""
    lines = [f"DRAFT STRATEGY: {strategy['label']}"]
    lines.append(f"- {strategy['description']}")
    pos_w = strategy.get("position_weights", {})
    if pos_w:
        premiums = ", ".join(f"{p} {w}x" for p, w in pos_w.items())
        lines.append(f"- Position premiums: {premiums}")
    else:
        lines.append("- Position premiums: (none)")
    tier_w = strategy.get("tier_weights", {})
    if tier_w:
        premiums = ", ".join(f"T{t} {w}x" for t, w in tier_w.items())
        lines.append(f"- Tier premiums: {premiums}")

    # Studs & Steals: inject tier-specific AI guidance
    if settings.draft_strategy == "studs_and_steals" and player_tier > 0:
        if player_tier == 1:
            lines.append("- STRATEGY NOTE: This is an ELITE player. Be aggressive — these are the studs you build your team around. Push to acquire even at slight overpay.")
        elif player_tier >= 2:
            lines.append("- STRATEGY NOTE: Evaluate this player as a potential STEAL. Look for upside catalysts: new team/role, coaching scheme changes, injury recovery, breakout trajectory, age-based upside, reduced competition for targets/touches. If below FMV AND has upside catalysts, flag as a steal worth targeting. If just cheap with no upside, it's a pass.")

    return "\n".join(lines) + "\n"


def _build_context(
    player_name: str,
    current_bid: float,
    engine: EngineAdvice,
    state: DraftState,
) -> str:
    """Build a strategic scouting prompt — called once per nomination."""
    my = state.my_team

    # Unfilled roster slots
    needs = [slot for slot, occupant in my.roster.items() if occupant is None]

    # Player info
    player_obj = state.get_player(player_name)
    pos = player_obj.projection.position.value if player_obj else "UNK"
    tier = player_obj.projection.tier if player_obj else "?"
    proj_pts = player_obj.projection.projected_points if player_obj else 0

    # Top remaining at this position (for alternatives analysis)
    same_pos_remaining = state.get_remaining_players(pos)
    alternatives = [
        {"name": p.projection.player_name, "tier": p.projection.tier,
         "vorp": round(p.vorp, 1), "fmv": round(p.projection.baseline_aav * state.get_inflation_factor(), 1)}
        for p in same_pos_remaining[:8]
        if p.projection.player_name.lower() != player_name.lower()
    ]

    # Top remaining at OTHER positions I still need
    other_needs = {}
    for slot, occupant in my.roster.items():
        if occupant is None:
            base = slot.split()[0]
            if base not in other_needs:
                remaining = state.get_remaining_players(base)[:3]
                other_needs[base] = [
                    {"name": p.projection.player_name, "fmv": round(p.projection.baseline_aav * state.get_inflation_factor(), 1)}
                    for p in remaining
                ]

    # Roster composition summary
    filled_positions = {}
    for slot, occupant in my.roster.items():
        base = slot.split()[0] if slot else slot
        if base not in filled_positions:
            filled_positions[base] = {"filled": 0, "total": 0}
        filled_positions[base]["total"] += 1
        if occupant:
            filled_positions[base]["filled"] += 1
    roster_summary = ", ".join(
        f"{p} {v['filled']}/{v['total']}" for p, v in sorted(filled_positions.items())
    )

    # Opponent demand for this position
    opponent_section = ""
    if hasattr(state, "opponent_tracker") and state.opponent_tracker:
        tracker = state.opponent_tracker
        remaining_at_pos = len(same_pos_remaining)
        demand = tracker.get_position_demand(pos, remaining_at_pos)
        threats = tracker.get_team_threat_levels()[:3]

        opponent_section = f"""
COMPETITION FOR {pos}:
- {demand['teams_needing']} of {state.opponent_tracker.team_rosters.__len__()} teams still need {pos}
- {remaining_at_pos} {pos}s still available in the pool
- Bidding war risk: {"HIGH — expect overpay" if demand.get('bidding_war_risk') else "LOW — less competition"}
- Wealthiest opponents: {json.dumps([{"budget": t["budget"], "spending_power": t["spending_power"]} for t in threats])}"""

    # Player news/injury status
    from player_news import get_player_status
    news = get_player_status(player_name)
    news_section = ""
    if news:
        news_section = f"\n\nPLAYER NEWS:\n- Status: {news['status']}"
        if news.get("injury"):
            news_section += f" ({news['injury']})"
        if news.get("injury_note"):
            news_section += f" — {news['injury_note']}"
        if not news.get("active"):
            news_section += "\n- WARNING: Player is marked INACTIVE"

    # VONA
    vona_note = ""
    if engine.vona and engine.vona > 0:
        vona_note = f"\n- VONA drop-off: {engine.vona:.1f} pts to next best"
        if engine.vona_next_player:
            vona_note += f" ({engine.vona_next_player})"

    # Recent price trends
    recent_picks = state.draft_log[-5:] if state.draft_log else []
    recent_str = json.dumps(recent_picks) if recent_picks else "None yet"

    return f"""You are an expert fantasy {settings.sport_name} analyst providing a quick scouting report for a live auction draft. A player was just nominated. Analyze whether I should target this player and how much to spend.

NOMINATED PLAYER:
- Name: {player_name}
- Position: {pos} (Tier {tier})
- Projected points (half-PPR): {proj_pts}
- Fair Market Value: ${engine.fmv} (inflation-adjusted)
- VORP (value over replacement): {engine.vorp:.1f}{vona_note}
- Positional scarcity multiplier: {engine.scarcity_multiplier}x

MY DRAFT SITUATION:
- Budget: ${my.budget} remaining of ${my.total_budget}
- Roster: {roster_summary}
- Open slots: {', '.join(needs) if needs else 'FULL — no need'}
- Players I own: {json.dumps(my.players_acquired)}
- Max I can bid (keeping $1/empty slot): ${my.max_bid}

{_build_strategy_context(player_tier=tier if isinstance(tier, int) else 0)}
ALTERNATIVES — other {pos}s still available:
{json.dumps(alternatives, indent=2)}

OTHER POSITIONS I STILL NEED:
{json.dumps(other_needs, indent=2)}
{opponent_section}

MARKET CONTEXT:
- Inflation: {state.get_inflation_factor():.3f}x (>1 = prices inflated, <1 = bargains likely)
- Total players remaining: {len(state.get_remaining_players())} of {len(state.players)}
- Recent sales: {recent_str}{news_section}

ANALYSIS REQUESTED:
1. Player outlook — is {player_name} projected for a strong 2026 season? Consider any coaching changes, offensive scheme, injury history, or teammate changes that affect their value.
2. Value assessment — is FMV ${engine.fmv} fair given the alternatives still available? Are there comparable players I could get cheaper later?
3. Roster fit — does my team need this position? Would spending here leave me thin elsewhere?
4. Max bid recommendation — given my budget, needs, and who's left, what's the most I should pay?

Respond with ONLY valid JSON (no markdown, no code fences):
{{"action": "BUY" or "PASS" or "PRICE_ENFORCE", "max_bid": <integer>, "reasoning": "<2-3 sentences covering outlook, value, and fit>"}}"""


async def get_ai_advice(
    player_name: str,
    current_bid: float,
    state: DraftState,
    engine_advice: EngineAdvice,
) -> FullAdvice:
    """
    Call Gemini for AI-enhanced advice. Falls back to engine-only if:
    - No API key configured
    - Gemini takes > ai_timeout_ms
    - Gemini returns invalid JSON

    Keyed by player name only — one Gemini call per nomination.
    Bid changes are handled by the engine; AI provides strategic context.
    """
    cache_key = player_name.lower().strip()

    if cache_key in _advice_cache:
        cached, ts = _advice_cache[cache_key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return cached

    global _rate_limit_until, ai_status

    # No API key — engine only
    if not _has_ai_key():
        ai_status = "no_key"
        return _engine_to_full(engine_advice, source="engine")

    # Rate limited — skip until backoff expires
    if time.time() < _rate_limit_until:
        remaining = int(_rate_limit_until - time.time())
        ai_status = f"rate_limited ({remaining}s)"
        return _engine_to_full(engine_advice, source="engine")

    # Skip if a call for this player is already in flight
    if cache_key in _inflight:
        return _engine_to_full(engine_advice, source="engine")

    _inflight.add(cache_key)
    try:
        context = _build_context(player_name, current_bid, engine_advice, state)

        result = await asyncio.wait_for(
            _call_ai(context),
            timeout=settings.ai_timeout_ms / 1000.0,
        )

        if result:
            action_str = result.get("action", engine_advice.action.value)
            try:
                action = AdviceAction(action_str)
            except ValueError:
                action = engine_advice.action

            advice = FullAdvice(
                action=action,
                max_bid=int(result.get("max_bid", engine_advice.max_bid)),
                fmv=engine_advice.fmv,
                inflation_rate=engine_advice.inflation_rate,
                reasoning=result.get("reasoning", engine_advice.reasoning),
                source="ai",
            )
            _advice_cache[cache_key] = (advice, time.time())
            ai_status = "ok"
            print(f"  [AI] Gemini advice for {player_name}: {advice.action.value}, max ${advice.max_bid}")
            return advice

    except asyncio.TimeoutError:
        ai_status = f"timeout ({settings.ai_timeout_ms}ms)"
        print(f"  [AI] Gemini timeout for {player_name} ({settings.ai_timeout_ms}ms)")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Parse Google's error to distinguish RPM vs daily quota
            reason = ""
            try:
                err_body = e.response.json()
                reason = err_body.get("error", {}).get("message", "")
            except Exception:
                reason = e.response.text[:200]

            is_daily = "RESOURCE_EXHAUSTED" in reason or "quota" in reason.lower() or "per day" in reason.lower()
            if is_daily:
                # Daily quota — don't retry until tomorrow
                _rate_limit_until = time.time() + 3600  # pause for 1 hour
                ai_status = "daily quota exhausted"
                print(f"  [AI] Gemini daily quota exhausted — disabling AI for 1h. Detail: {reason[:150]}")
            else:
                _rate_limit_until = time.time() + _RATE_LIMIT_BACKOFF_SECONDS
                ai_status = f"rate_limited ({_RATE_LIMIT_BACKOFF_SECONDS}s)"
                print(f"  [AI] Gemini 429 rate limited — pausing {_RATE_LIMIT_BACKOFF_SECONDS}s. Detail: {reason[:150]}")
        else:
            ai_status = f"error: HTTP {e.response.status_code}"
            print(f"  [AI] Gemini HTTP {e.response.status_code} for {player_name}")
    except Exception as e:
        ai_status = f"error: {type(e).__name__}"
        print(f"  [AI] Gemini error for {player_name}: {type(e).__name__}: {e}")
    finally:
        _inflight.discard(cache_key)

    fallback = _engine_to_full(engine_advice, source="engine")
    _advice_cache[cache_key] = (fallback, time.time())
    return fallback


def _has_ai_key() -> bool:
    """Check if any AI provider is configured."""
    provider = settings.ai_provider.lower()
    if provider == "claude":
        return bool(settings.anthropic_api_key and not settings.anthropic_api_key.startswith("your-"))
    else:
        return bool(settings.gemini_api_key and not settings.gemini_api_key.startswith("your-"))


async def _call_ai(prompt: str) -> Optional[dict]:
    """Route to the configured AI provider."""
    provider = settings.ai_provider.lower()
    if provider == "claude":
        return await _call_claude(prompt)
    else:
        return await _call_gemini(prompt)


async def _call_gemini(prompt: str) -> Optional[dict]:
    """Raw HTTP call to Gemini REST API."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    headers = {"Content-Type": "application/json"}
    params = {"key": settings.gemini_api_key}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 512,
            "responseMimeType": "application/json",
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, json=body, params=params, headers=headers, timeout=10.0
        )
        resp.raise_for_status()

    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


async def _call_claude(prompt: str) -> Optional[dict]:
    """Raw HTTP call to Anthropic Messages API."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": settings.claude_model,
        "max_tokens": 512,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=headers, timeout=10.0)
        resp.raise_for_status()

    data = resp.json()
    text = data["content"][0]["text"]

    # Claude may wrap JSON in markdown code fences — strip them
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]  # remove ```json line
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    return json.loads(cleaned)


async def get_draft_grade(prompt: str) -> Optional[dict]:
    """Call AI provider with extended timeout for post-draft grading."""
    if not _has_ai_key():
        return None
    try:
        return await asyncio.wait_for(
            _call_ai_text(prompt),
            timeout=10.0,
        )
    except Exception:
        return None


async def _call_ai_text(prompt: str) -> Optional[dict]:
    """Call configured AI provider for text responses (grading)."""
    provider = settings.ai_provider.lower()
    if provider == "claude":
        return await _call_claude(prompt)
    else:
        return await _call_gemini_text(prompt)


async def _call_gemini_text(prompt: str, timeout: float = 5.0) -> Optional[dict]:
    """Raw HTTP call to Gemini REST API returning plain text (for grading)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    headers = {"Content-Type": "application/json"}
    params = {"key": settings.gemini_api_key}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, json=body, params=params, headers=headers, timeout=timeout
        )
        resp.raise_for_status()

    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


def _engine_to_full(engine: EngineAdvice, source: str = "engine") -> FullAdvice:
    """Convert an EngineAdvice to a FullAdvice."""
    return FullAdvice(
        action=engine.action,
        max_bid=engine.max_bid,
        fmv=engine.fmv,
        inflation_rate=engine.inflation_rate,
        reasoning=engine.reasoning,
        source=source,
    )


async def precompute_advice(
    player_name: str, current_bid: float, state: DraftState
):
    """Fire-and-forget pre-computation triggered from /draft_update."""
    engine_advice = get_engine_advice(player_name, current_bid, state)
    await get_ai_advice(player_name, current_bid, state, engine_advice)
