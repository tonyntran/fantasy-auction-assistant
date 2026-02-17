"""Roster optimizer — greedily fills remaining roster by VORP/$ ratio."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import DraftState

from engine import calculate_fmv, calculate_strategy_multiplier
from config import settings


def get_optimal_plan(state: "DraftState") -> dict:
    """Compute optimal remaining picks for my team's current budget and needs."""
    needs = state.get_positional_need()
    remaining_budget = state.my_team.budget

    optimal_picks = []
    used_players: set[str] = set()

    for _ in range(settings.roster_size):
        if remaining_budget <= 0 or not any(v > 0 for v in needs.values()):
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
            if pick_cost > remaining_budget:
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
        })
        used_players.add(ps.projection.player_name)
        remaining_budget -= pick_cost
        needs[p_pos] = needs.get(p_pos, 0) - 1

    total_projected = sum(
        state.get_player(p["player"]).projection.projected_points
        for p in optimal_picks
        if state.get_player(p["player"])
    )

    return {
        "optimal_picks": optimal_picks,
        "remaining_budget_after": remaining_budget,
        "total_estimated_cost": state.my_team.budget - remaining_budget,
        "projected_points_added": round(total_projected, 1),
        "slots_to_fill": sum(1 for v in state.get_positional_need().values() if v > 0),
    }
