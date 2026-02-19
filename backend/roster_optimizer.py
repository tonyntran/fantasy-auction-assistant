"""Roster optimizer — greedily fills remaining roster by VORP/$ ratio."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import DraftState

from engine import calculate_fmv, calculate_strategy_multiplier
from config import settings


def get_optimal_plan(state: "DraftState") -> dict:
    """Compute optimal remaining picks for my team's current budget and needs.
    Phase 1: Fill starter slots with VORP/$ optimization.
    Phase 2: Fill bench slots at $1 each with best available VORP."""
    starter_needs = state.get_starter_need()
    remaining_budget = state.my_team.budget
    bench_spots = state.my_team.bench_spots_remaining

    # Reserve $1 per bench spot so we don't overspend on starters
    bench_reserve = bench_spots
    starter_budget = remaining_budget - bench_reserve

    optimal_picks = []
    used_players: set[str] = set()

    # Phase 1: Fill starter slots
    needs = dict(starter_needs)
    for _ in range(settings.roster_size):
        if starter_budget <= 0 or not any(v > 0 for v in needs.values()):
            break

        best = None
        best_ratio = -1.0

        for ps in state.get_remaining_players():
            if ps.projection.player_name in used_players:
                continue
            p_pos = ps.projection.position.value
            if needs.get(p_pos, 0) <= 0:
                continue
            fmv = calculate_fmv(ps, state)
            pick_cost = max(1, int(fmv * 0.85))  # estimate ~15% discount
            if pick_cost > starter_budget:
                continue
            strategy_mult = calculate_strategy_multiplier(ps, state)
            ratio = (ps.vorp * strategy_mult) / max(pick_cost, 1)
            if ratio > best_ratio:
                best_ratio = ratio
                best = (ps, pick_cost, fmv)

        if not best:
            break

        ps, pick_cost, fmv = best
        p_pos = ps.projection.position.value
        optimal_picks.append({
            "player": ps.projection.player_name,
            "position": p_pos,
            "estimated_price": pick_cost,
            "fmv": round(fmv, 1),
            "vorp": round(ps.vorp, 1),
            "tier": ps.projection.tier,
            "is_bench": False,
        })
        used_players.add(ps.projection.player_name)
        starter_budget -= pick_cost
        needs[p_pos] = needs.get(p_pos, 0) - 1

    # Phase 2: Fill bench slots at $1 each with best available VORP
    bench_picks = []
    for _ in range(bench_spots):
        best = None
        best_vorp = -1.0

        for ps in state.get_remaining_players():
            if ps.projection.player_name in used_players:
                continue
            if ps.vorp > best_vorp:
                best_vorp = ps.vorp
                best = ps

        if not best:
            break

        bench_picks.append({
            "player": best.projection.player_name,
            "position": best.projection.position.value,
            "estimated_price": 1,
            "fmv": round(calculate_fmv(best, state), 1),
            "vorp": round(best.vorp, 1),
            "tier": best.projection.tier,
            "is_bench": True,
        })
        used_players.add(best.projection.player_name)

    all_picks = optimal_picks + bench_picks

    total_projected = sum(
        state.get_player(p["player"]).projection.projected_points
        for p in all_picks
        if state.get_player(p["player"])
    )

    starter_cost = sum(p["estimated_price"] for p in optimal_picks)
    bench_cost = sum(p["estimated_price"] for p in bench_picks)
    total_cost = starter_cost + bench_cost

    return {
        "optimal_picks": all_picks,
        "starter_picks": optimal_picks,
        "bench_picks": bench_picks,
        "remaining_budget_after": remaining_budget - total_cost,
        "total_estimated_cost": total_cost,
        "starter_cost": starter_cost,
        "bench_cost": bench_cost,
        "projected_points_added": round(total_projected, 1),
        "slots_to_fill": sum(1 for v in starter_needs.values() if v > 0),
        "bench_to_fill": bench_spots,
    }
