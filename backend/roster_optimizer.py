"""Roster optimizer — greedily fills remaining roster by VORP/$ ratio."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import DraftState

from engine import calculate_fmv, calculate_strategy_multiplier
from config import settings


def _estimate_price(fmv: float, tier: int) -> int:
    """Estimate realistic auction price based on FMV and tier.
    Elite players go at or above FMV (bidding wars), mid-tier at FMV,
    low-tier at a discount (less competition)."""
    if tier <= 1:
        return max(1, int(fmv * 1.10))   # elite: expect 10% premium
    elif tier == 2:
        return max(1, int(fmv * 1.0))    # high: expect to pay FMV
    elif tier == 3:
        return max(1, int(fmv * 0.90))   # mid: modest 10% discount
    else:
        return max(1, int(fmv * 0.75))   # deep: 25% discount, less demand


def get_optimal_plan(state: "DraftState") -> dict:
    """Compute optimal remaining picks for my team's current budget and needs.
    Phase 1: Fill starter slots with VORP/$ optimization.
    Phase 2: Fill bench slots with realistic prices for cheap remaining players."""
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
            pick_cost = _estimate_price(fmv, ps.projection.tier)
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

    # Phase 2: Fill bench slots with upside skill players (RB/WR/TE)
    # Enforce position caps: K=1, DEF=1, QB=2 across entire roster
    pos_caps = {"K": 1, "DEF": 1, "QB": 2}
    pos_counts: dict[str, int] = {}
    for p in state.my_team.players_acquired:
        pos_counts[p["position"]] = pos_counts.get(p["position"], 0) + 1
    for p in optimal_picks:
        pos_counts[p["position"]] = pos_counts.get(p["position"], 0) + 1

    # Bench preference: RB/WR get priority (upside handcuffs/breakouts)
    bench_upside = {"RB": 1.3, "WR": 1.3, "TE": 1.0}

    bench_budget = remaining_budget - sum(p["estimated_price"] for p in optimal_picks)
    bench_picks = []
    for _ in range(bench_spots):
        if bench_budget <= 0:
            break
        best = None
        best_score = -1.0
        best_cost = 0

        for ps in state.get_remaining_players():
            if ps.projection.player_name in used_players:
                continue
            p_pos = ps.projection.position.value
            # Skip positions at their cap
            cap = pos_caps.get(p_pos)
            if cap is not None and pos_counts.get(p_pos, 0) >= cap:
                continue
            # Bench = skill positions only (RB, WR, TE)
            if p_pos not in bench_upside:
                continue
            fmv = calculate_fmv(ps, state)
            pick_cost = max(1, int(fmv * 0.75))
            if pick_cost > bench_budget:
                continue
            score = ps.vorp * bench_upside.get(p_pos, 1.0)
            if score > best_score:
                best_score = score
                best = ps
                best_cost = pick_cost

        if not best:
            break

        p_pos = best.projection.position.value
        bench_picks.append({
            "player": best.projection.player_name,
            "position": p_pos,
            "estimated_price": best_cost,
            "fmv": round(calculate_fmv(best, state), 1),
            "vorp": round(best.vorp, 1),
            "tier": best.projection.tier,
            "is_bench": True,
        })
        used_players.add(best.projection.player_name)
        pos_counts[p_pos] = pos_counts.get(p_pos, 0) + 1
        bench_budget -= best_cost

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
