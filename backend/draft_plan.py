"""
AI Draft Plan — on-demand strategic spending plan combining optimizer output
with AI analysis of market dynamics, opponent pressure, and spending allocation.

Triggered by button click, cached with staleness tracking,
auto-invalidated when players are drafted.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from state import DraftState

from config import settings
from ai_advisor import get_http_client
from engine import calculate_fmv
from roster_optimizer import get_optimal_plan


# -----------------------------------------------------------------
# Module-level cache
# -----------------------------------------------------------------

_cached_plan: Optional[dict] = None
_picks_at_cache: int = 0


def invalidate_plan():
    """Clear the cached plan (called when players are drafted)."""
    global _cached_plan, _picks_at_cache
    _cached_plan = None
    _picks_at_cache = 0


def get_picks_since_plan(state: "DraftState") -> Optional[int]:
    """Return how many picks have happened since the plan was generated.
    Returns None if no plan has been generated yet."""
    if _cached_plan is None:
        return None
    return len(state.draft_log) - _picks_at_cache


# -----------------------------------------------------------------
# Prompt builder
# -----------------------------------------------------------------

def build_draft_plan_prompt(state: "DraftState") -> str:
    """Build AI prompt for strategic draft plan."""
    my = state.my_team
    starter_needs = state.get_starter_need()
    optimizer = get_optimal_plan(state)
    inflation = state.get_inflation_factor()
    bench_spots = my.bench_spots_remaining

    # My roster summary with projected points
    filled = [p for p in my.players_acquired]
    roster_lines = []
    roster_pts = 0
    for p in filled:
        ps = state.get_player(p['name'])
        pts = round(ps.projection.projected_points, 1) if ps else 0
        roster_pts += pts
        roster_lines.append(f"  {p['name']} ({p['position']}) — ${p['price']}, {pts} pts")
    roster_str = "\n".join(roster_lines) if roster_lines else "  (empty)"

    # Open STARTER slots (bench excluded — those are $1 fills)
    open_slots = {pos: count for pos, count in starter_needs.items() if count > 0}
    slots_to_fill = sum(open_slots.values())

    # Spendable budget = total minus $1 per bench spot
    spendable_budget = my.budget - bench_spots
    budget_per_slot = round(spendable_budget / slots_to_fill, 1) if slots_to_fill > 0 else 0

    # Top 5 remaining per needed position — include projected points prominently
    position_pools = {}
    for pos, count in open_slots.items():
        remaining = state.get_remaining_players(pos)[:5]
        pool = []
        for ps in remaining:
            fmv = calculate_fmv(ps, state)
            pool.append({
                "name": ps.projection.player_name,
                "tier": ps.projection.tier,
                "fmv": round(fmv, 1),
                "vorp": round(ps.vorp, 1),
                "pts": round(ps.projection.projected_points, 1),
            })
        if pool:
            position_pools[pos] = pool

    # Optimizer baseline (compact) — labeled as conservative floor
    opt_baseline = []
    opt_total_pts = 0
    for pick in optimizer.get("optimal_picks", [])[:8]:
        opt_baseline.append(f"  {pick['player']} ({pick['position']}) ~${pick['estimated_price']}, VORP {pick.get('vorp', 0)}")
        ps = state.get_player(pick['player'])
        if ps:
            opt_total_pts += ps.projection.projected_points
    opt_str = "\n".join(opt_baseline) if opt_baseline else "  (no picks available)"

    # Top 3 opponent threats
    opponent_section = ""
    if hasattr(state, "opponent_tracker") and state.opponent_tracker:
        threats = state.opponent_tracker.get_team_threat_levels()[:3]
        if threats:
            threat_lines = []
            for t in threats:
                name = state.apply_alias(t.get("team_name", f"Team {t.get('team_id')}"))
                threat_lines.append(
                    f"  {name}: ${t['budget']} budget, "
                    f"needs {', '.join(t.get('top_needs', [])[:3])}"
                )
            opponent_section = "TOP OPPONENT THREATS:\n" + "\n".join(threat_lines)

    # Strategy context
    strategy_label = settings.active_strategy["label"]
    strategy_desc = settings.active_strategy["description"]

    return f"""You are an expert fantasy {settings.sport_name} auction draft strategist. Your goal is to BUILD THE STRONGEST POSSIBLE STARTING LINEUP — not to find bargains or save money.

CORE PRINCIPLE: Every dollar left unspent at the end of the draft is a wasted dollar. Bench spots are filled at $1 each (${bench_spots} bench spots = ${bench_spots} reserved). The goal is to MAXIMIZE TOTAL STARTING LINEUP PROJECTED POINTS by spending aggressively on high-upside starters.

MY DRAFT SITUATION:
- Total budget: ${my.budget} remaining of ${my.total_budget}
- Spendable on starters: ${spendable_budget} (after ${bench_spots} bench spots at $1 each)
- Open starter slots: {json.dumps(open_slots)} ({slots_to_fill} total)
- Budget per starter slot: ${budget_per_slot} average available
- Inflation: {inflation:.3f}x
- Current roster points: {round(roster_pts, 1)} pts

MY CURRENT ROSTER:
{roster_str}

DRAFT STRATEGY: {strategy_label} — {strategy_desc}

TOP AVAILABLE PLAYERS BY POSITION (sorted by projected points):
{json.dumps(position_pools, indent=2)}

OPTIMIZER BASELINE (conservative VORP/$ value picks — this is the FLOOR, not the target):
{opt_str}
  Est. cost: ${optimizer.get('total_estimated_cost', 0)} | +{round(opt_total_pts, 1)} pts | ${my.budget - optimizer.get('total_estimated_cost', 0)} WASTED

{opponent_section}

CRITICAL INSTRUCTIONS:
- SPEND AGGRESSIVELY on starters. Allocate all ${spendable_budget} across starting slots. Bench spots are already reserved at $1 each.
- TARGET THE BEST PLAYERS, not the best value. A Tier 1 player at FMV is better than a Tier 3 player at 50% off.
- The optimizer baseline above is the conservative floor — your plan should aim HIGHER on projected points by targeting premium players even if it means paying FMV or slightly above.
- Identify which 1-2 positions to splurge on (get elite talent) and which 1-2 to fill cheaply.
- Price ranges should reflect what you'd actually need to pay, not bargain-hunting hopes.
- Also identify 1-2 bargain picks — players who could outperform their price due to situation, upside, or market inefficiency. These are value plays to pair with your premium targets.

Respond with ONLY valid JSON (no markdown, no code fences):
{{
  "strategy_summary": "2-3 sentence overview",
  "spending_plan": [
    {{"position": "WR", "budget_allocation": 35, "tier_target": "elite", "reasoning": "..."}}
  ],
  "key_targets": [
    {{"player": "Name", "position": "WR", "price_range": [28, 35], "priority": "must-have", "reasoning": "..."}}
  ],
  "bargain_picks": [
    {{"player": "Name", "position": "RB", "price_range": [3, 8], "reasoning": "..."}}
  ],
  "avoid_list": ["names to let opponents overpay for"],
  "budget_reserve": {bench_spots}
}}

Priority values: "must-have", "strong-target", "nice-to-have"
spending_plan: one entry per position with open starter slots. budget_allocation MUST sum to roughly ${spendable_budget}.
Key targets: 3-5 premium players. Bargain picks: 1-2 value sleepers. Avoid list: 1-3 players.
Keep reasoning fields under 15 words. Be concise."""


# -----------------------------------------------------------------
# Fallback plan (engine-only, derived from optimizer)
# -----------------------------------------------------------------

def _fallback_plan(state: "DraftState") -> dict:
    """Build a plan purely from optimizer output when AI is unavailable.
    Distributes full budget across starter positions — bench at $1 each."""
    optimizer = get_optimal_plan(state)
    starter_needs = state.get_starter_need()
    my = state.my_team
    bench_spots = my.bench_spots_remaining
    open_slots = {pos: count for pos, count in starter_needs.items() if count > 0}
    slots_to_fill = sum(open_slots.values())
    bench_reserve = bench_spots  # $1 per bench spot

    # Build spending plan from starter picks only
    spending_by_pos: dict[str, dict] = {}
    for pick in optimizer.get("starter_picks", optimizer.get("optimal_picks", [])):
        if pick.get("is_bench"):
            continue
        pos = pick["position"]
        if pos not in spending_by_pos:
            spending_by_pos[pos] = {"budget": 0, "count": 0, "top_tier": pick.get("tier", 3)}
        spending_by_pos[pos]["budget"] += pick["estimated_price"]
        spending_by_pos[pos]["count"] += 1
        spending_by_pos[pos]["top_tier"] = min(spending_by_pos[pos]["top_tier"], pick.get("tier", 3))

    # Ensure ALL open positions are represented, even if optimizer missed them
    spendable = my.budget - bench_reserve
    for pos, count in open_slots.items():
        if pos not in spending_by_pos:
            # Estimate budget from remaining players at this position
            remaining = state.get_remaining_players(pos)[:count]
            est_budget = sum(calculate_fmv(p, state) for p in remaining)
            top_tier = remaining[0].projection.tier if remaining else 3
            spending_by_pos[pos] = {"budget": round(est_budget), "count": count, "top_tier": top_tier}

    # Scale allocations up to use full spendable budget
    total_opt_cost = sum(info["budget"] for info in spending_by_pos.values())
    scale = spendable / total_opt_cost if total_opt_cost > 0 else 1.0

    spending_plan = []
    tier_labels = {1: "elite", 2: "high", 3: "mid", 4: "low", 5: "deep"}
    for pos, info in spending_by_pos.items():
        scaled_budget = round(info["budget"] * scale)
        spending_plan.append({
            "position": pos,
            "budget_allocation": scaled_budget,
            "tier_target": tier_labels.get(info["top_tier"], "mid"),
            "reasoning": f"{info['count']} slot(s) — target best available",
        })

    # Key targets from starter picks — price at FMV, not discount
    key_targets = []
    starter_picks = [p for p in optimizer.get("optimal_picks", []) if not p.get("is_bench")]
    for pick in starter_picks[:5]:
        fmv = pick.get("fmv", pick["estimated_price"])
        low = max(1, int(fmv * 0.85))
        high = int(fmv * 1.15)
        key_targets.append({
            "player": pick["player"],
            "position": pick["position"],
            "price_range": [low, high],
            "priority": "must-have" if pick.get("vorp", 0) > 10 else "strong-target" if pick.get("vorp", 0) > 5 else "nice-to-have",
            "reasoning": f"VORP {pick.get('vorp', 0)}, {round(pick.get('fmv', 0))} pts proj",
        })

    total_allocated = sum(s["budget_allocation"] for s in spending_plan)
    reserve = max(bench_reserve, my.budget - total_allocated)

    return {
        "strategy_summary": (
            f"Spend ${spendable} aggressively across {slots_to_fill} starter slots. "
            f"Bench fills at $1 each (${bench_reserve} reserved). Every unspent dollar is wasted."
        ),
        "spending_plan": spending_plan,
        "key_targets": key_targets,
        "avoid_list": [],
        "budget_reserve": reserve,
        "source": "engine",
    }


# -----------------------------------------------------------------
# Dedicated AI call with higher token limit for draft plan
# -----------------------------------------------------------------

async def _call_draft_plan_ai(prompt: str) -> Optional[dict]:
    """Call AI provider with 2048 max output tokens for the draft plan."""
    provider = settings.ai_provider.lower()
    if provider == "claude":
        return await _call_draft_plan_claude(prompt)
    return await _call_draft_plan_gemini(prompt)


async def _call_draft_plan_gemini(prompt: str) -> Optional[dict]:
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
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    client = get_http_client()
    resp = await client.post(
        url, json=body, params=params, headers=headers, timeout=15.0
    )
    resp.raise_for_status()

    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    result = _try_parse_json(text)
    if result is None:
        raise json.JSONDecodeError("Failed to parse Gemini response", text, 0)
    return result


async def _call_draft_plan_claude(prompt: str) -> Optional[dict]:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": settings.claude_model,
        "max_tokens": 2048,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }

    client = get_http_client()
    resp = await client.post(url, json=body, headers=headers, timeout=15.0)
    resp.raise_for_status()

    data = resp.json()
    text = data["content"][0]["text"]

    result = _try_parse_json(text)
    if result is None:
        raise json.JSONDecodeError("Failed to parse Claude response", text, 0)
    return result


def _try_parse_json(text: str) -> Optional[dict]:
    """Attempt to parse JSON, with repair for common truncation issues."""
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # Truncation repair: close open strings/arrays/objects
    repaired = cleaned
    # Close any unterminated string
    if repaired.count('"') % 2 == 1:
        repaired += '"'
    # Close brackets/braces
    open_braces = repaired.count('{') - repaired.count('}')
    open_brackets = repaired.count('[') - repaired.count(']')
    repaired += ']' * max(0, open_brackets)
    repaired += '}' * max(0, open_braces)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


# -----------------------------------------------------------------
# AI draft plan entry point
# -----------------------------------------------------------------

async def get_ai_draft_plan(state: "DraftState") -> dict:
    """Generate or return cached AI draft plan."""
    global _cached_plan, _picks_at_cache

    # Return cache if present
    if _cached_plan is not None:
        plan = dict(_cached_plan)
        plan["picks_since_plan"] = len(state.draft_log) - _picks_at_cache
        return plan

    from ai_advisor import _has_ai_key

    if not _has_ai_key():
        plan = _fallback_plan(state)
        _cached_plan = plan
        _picks_at_cache = len(state.draft_log)
        plan["picks_since_plan"] = 0
        return plan

    try:
        prompt = build_draft_plan_prompt(state)
        result = await asyncio.wait_for(
            _call_draft_plan_ai(prompt),
            timeout=20.0,
        )

        if result and isinstance(result, dict):
            if "strategy_summary" in result:
                result["source"] = "ai"
                _cached_plan = result
                _picks_at_cache = len(state.draft_log)
                result["picks_since_plan"] = 0
                return result

    except asyncio.TimeoutError:
        print("  [DraftPlan] AI timeout (20s)")
    except json.JSONDecodeError as e:
        # Try to repair truncated JSON from the raw response
        print(f"  [DraftPlan] JSON parse failed, attempting repair...")
        # Re-fetch raw text isn't possible here, fall through to fallback
    except Exception as e:
        print(f"  [DraftPlan] AI error: {type(e).__name__}: {e}")

    # Fallback to engine-only plan
    plan = _fallback_plan(state)
    _cached_plan = plan
    _picks_at_cache = len(state.draft_log)
    plan["picks_since_plan"] = 0
    return plan
