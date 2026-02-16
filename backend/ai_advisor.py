"""
AI advisor module — async Gemini 1.5 Flash integration with timeout, fallback, and caching.
Falls back to pure engine advice if the AI is slow, unavailable, or misconfigured.

Features:
  - Richer context (opponent model, ADP, recent picks, team synergy)
  - Streaming via Gemini streamGenerateContent
  - Post-draft grading with extended timeout
"""

import asyncio
import json
import time
from typing import Optional, AsyncGenerator

import httpx

from models import EngineAdvice, FullAdvice, AdviceAction
from state import DraftState
from config import settings
from engine import get_engine_advice


# In-memory cache: (player_name_lower, bid_bucket) -> (FullAdvice, timestamp)
_advice_cache: dict[tuple[str, int], tuple[FullAdvice, float]] = {}
CACHE_TTL_SECONDS = 10


def _build_context(
    player_name: str,
    current_bid: float,
    engine: EngineAdvice,
    state: DraftState,
) -> str:
    """Build a structured prompt for Gemini with all relevant draft context."""
    my = state.my_team

    # Unfilled roster slots
    needs = [slot for slot, occupant in my.roster.items() if occupant is None]

    # Top remaining players by position
    top_remaining = {}
    for pos in settings.display_positions:
        players = state.get_remaining_players(pos)[:5]
        top_remaining[pos] = [
            {
                "name": p.projection.player_name,
                "vorp": round(p.vorp, 1),
                "aav": p.projection.baseline_aav,
            }
            for p in players
        ]

    # Recent draft picks (price trend context)
    recent_picks = state.draft_log[-5:] if state.draft_log else []
    recent_str = json.dumps(recent_picks) if recent_picks else "No picks yet"

    # Opponent analysis (condensed)
    opponent_section = ""
    if hasattr(state, "opponent_tracker") and state.opponent_tracker:
        tracker = state.opponent_tracker
        player_obj = state.get_player(player_name)
        pos = player_obj.projection.position.value if player_obj else "UNK"
        remaining_at_pos = len(state.get_remaining_players(pos))
        demand = tracker.get_position_demand(pos, remaining_at_pos)
        threats = tracker.get_team_threat_levels()[:3]  # Top 3 spenders

        opponent_section = f"""
OPPONENT ANALYSIS:
- {demand['teams_needing']} teams still need {pos}, {demand['players_remaining']} available
- Bidding war risk: {"HIGH" if demand.get('bidding_war_risk') else "LOW"}
- Top spenders: {json.dumps([{"budget": t["budget"], "power": t["spending_power"]} for t in threats])}"""

    # ADP comparison
    adp_note = ""
    if engine.adp_value:
        adp_note = f"\n- Market ADP value: ${engine.adp_value:.0f} (compare to FMV ${engine.fmv})"

    return f"""You are an expert fantasy {settings.sport_name} auction draft advisor. Provide a JSON response.

CURRENT SITUATION:
- Player nominated: {player_name}
- Current bid: ${int(current_bid)}
- Engine FMV: ${engine.fmv} (inflation-adjusted)
- Engine VORP: {engine.vorp:.1f}
- Scarcity multiplier: {engine.scarcity_multiplier}x
- Engine recommendation: {engine.action.value}{adp_note}

MY TEAM:
- Budget remaining: ${my.budget} of ${my.total_budget}
- Roster needs (unfilled slots): {', '.join(needs) if needs else 'FULL'}
- Players acquired: {json.dumps(my.players_acquired)}
- Max affordable bid: ${my.max_bid}

ROOM STATE:
- Inflation factor: {state.get_inflation_factor():.3f} (>1 = money is loose, <1 = tight)
- Players remaining: {len(state.get_remaining_players())} of {len(state.players)}
- Recent picks: {recent_str}
{opponent_section}

TOP REMAINING BY POSITION:
{json.dumps(top_remaining, indent=2)}

Consider: roster construction, positional scarcity, opponent needs, whether better value
may be available later, and team composition synergy with my current players.

Respond with ONLY valid JSON (no markdown, no explanation outside the JSON):
{{"action": "BUY" or "PASS" or "PRICE_ENFORCE", "max_bid": <integer>, "reasoning": "<1-2 sentences>"}}"""


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
    """
    # Check cache (bucket bids into $2 increments to reduce duplicates)
    bid_bucket = int(current_bid) // 2 * 2
    cache_key = (player_name.lower().strip(), bid_bucket)

    if cache_key in _advice_cache:
        cached, ts = _advice_cache[cache_key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return cached

    # No API key — engine only
    if not settings.gemini_api_key or settings.gemini_api_key.startswith("your-"):
        return _engine_to_full(engine_advice, source="engine")

    context = _build_context(player_name, current_bid, engine_advice, state)

    try:
        result = await asyncio.wait_for(
            _call_gemini(context),
            timeout=settings.ai_timeout_ms / 1000.0,
        )

        if result:
            action_str = result.get("action", engine_advice.action.value)
            # Validate action is one of our known actions
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
            return advice

    except asyncio.TimeoutError:
        pass  # Fall through to engine
    except Exception:
        pass  # Fall through to engine

    fallback = _engine_to_full(engine_advice, source="engine")
    _advice_cache[cache_key] = (fallback, time.time())
    return fallback


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
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, json=body, params=params, headers=headers, timeout=5.0
        )
        resp.raise_for_status()

    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


async def _call_gemini_text(prompt: str, timeout: float = 5.0) -> Optional[str]:
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


async def stream_ai_advice(
    player_name: str,
    current_bid: float,
    state: DraftState,
    engine_advice: EngineAdvice,
) -> AsyncGenerator[str, None]:
    """Generator that yields text chunks from Gemini streaming API."""
    if not settings.gemini_api_key or settings.gemini_api_key.startswith("your-"):
        yield engine_advice.reasoning
        return

    context = _build_context(player_name, current_bid, engine_advice, state)

    # Use streaming endpoint
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:streamGenerateContent"
    )
    params = {"key": settings.gemini_api_key, "alt": "sse"}
    body = {
        "contents": [{"parts": [{"text": context}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 256,
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=body, params=params, timeout=5.0
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            text = (
                                data.get("candidates", [{}])[0]
                                .get("content", {})
                                .get("parts", [{}])[0]
                                .get("text", "")
                            )
                            if text:
                                yield text
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
    except Exception as e:
        yield f"[AI streaming error: {e}. Using engine advice.]"
        yield f"\n{engine_advice.reasoning}"


async def get_draft_grade(prompt: str) -> Optional[dict]:
    """Call Gemini with extended timeout for post-draft grading."""
    if not settings.gemini_api_key or settings.gemini_api_key.startswith("your-"):
        return None
    try:
        return await asyncio.wait_for(
            _call_gemini_text(prompt, timeout=10.0),
            timeout=10.0,
        )
    except Exception:
        return None


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
