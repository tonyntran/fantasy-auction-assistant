"""
Nomination strategy engine — suggests who to nominate when it's your turn.

Three strategies:
  BUDGET_DRAIN:       Expensive players you DON'T need → drain rival budgets
  RIVAL_DESPERATION:  High-scarcity positions you don't need → start bidding wars
  BARGAIN_SNAG:       Low-FMV players you DO need → snag cheaply
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import DraftState

from engine import calculate_fmv, calculate_scarcity_multiplier
from config import settings


def get_nomination_suggestions(state: "DraftState", top_n: int = 5) -> list[dict]:
    """Generate ranked nomination suggestions with strategy reasoning."""
    remaining = state.get_remaining_players()
    my_needs = state.get_positional_need()

    suggestions = []

    for ps in remaining:
        pos = ps.projection.position.value
        fmv = calculate_fmv(ps, state)
        scarcity = calculate_scarcity_multiplier(ps, state)
        my_need_count = my_needs.get(pos, 0)

        # Strategy A: Budget Drain — nominate expensive players you don't need
        if my_need_count == 0 and fmv > 20:
            suggestions.append({
                "player_name": ps.projection.player_name,
                "position": pos,
                "fmv": round(fmv, 1),
                "strategy": "BUDGET_DRAIN",
                "reasoning": f"You don't need {pos}. Nominate to force rivals to spend ${fmv:.0f}+.",
                "priority": round(fmv * 0.8, 1),
            })

        # Strategy B: Rival Desperation — high scarcity positions you've filled
        if scarcity >= 1.15 and my_need_count == 0:
            # Check opponent demand if available
            demand_info = ""
            if state.opponent_tracker:
                remaining_at_pos = len(state.get_remaining_players(pos))
                demand = state.opponent_tracker.get_position_demand(pos, remaining_at_pos)
                if demand.get("bidding_war_risk"):
                    demand_info = f" {demand['teams_needing']} teams fighting."
            suggestions.append({
                "player_name": ps.projection.player_name,
                "position": pos,
                "fmv": round(fmv, 1),
                "strategy": "RIVAL_DESPERATION",
                "reasoning": f"{pos} scarcity is {scarcity:.2f}x. Rivals will overpay.{demand_info}",
                "priority": round(fmv * scarcity, 1),
            })

        # Strategy C: Bargain Snag — cheap players you need (late-draft)
        if my_need_count > 0 and fmv < 10 and ps.vorp > 0:
            suggestions.append({
                "player_name": ps.projection.player_name,
                "position": pos,
                "fmv": round(fmv, 1),
                "strategy": "BARGAIN_SNAG",
                "reasoning": f"You need {pos}. Low FMV ${fmv:.0f} — might get a deal.",
                "priority": round(ps.vorp * 2, 1),
            })

    # Deduplicate: keep highest-priority entry per player
    seen = {}
    for s in suggestions:
        name = s["player_name"]
        if name not in seen or s["priority"] > seen[name]["priority"]:
            seen[name] = s

    result = sorted(seen.values(), key=lambda s: s["priority"], reverse=True)
    return result[:top_n]
