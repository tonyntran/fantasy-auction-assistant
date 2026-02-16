"""
End-of-draft $1 targeting — identifies quality players likely to go for $1-3
as team budgets deplete. Maintained as a live "sleeper watch" list.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import DraftState

from engine import calculate_fmv
from config import settings


def get_sleeper_candidates(state: "DraftState", max_results: int = 10) -> list[dict]:
    """
    Identify undrafted players likely to go for $1-3.

    A player becomes a sleeper target when:
    1. They have positive VORP (they're actually good)
    2. Most teams are budget-constrained
    3. Their FMV is in the moderate range ($3-25)
    """
    remaining = state.get_remaining_players()

    # Count budget-constrained teams (effective spending power <= $5)
    constrained_teams = 0
    total_teams = 0
    for budget in state.team_budgets.values():
        total_teams += 1
        if budget <= 10:
            constrained_teams += 1

    if total_teams == 0:
        total_teams = settings.league_size
    constraint_ratio = constrained_teams / total_teams

    candidates = []
    for ps in remaining:
        if ps.vorp <= 0:
            continue

        fmv = calculate_fmv(ps, state)

        # Skip players too cheap (kickers/DEF) or too expensive (elite)
        if fmv < 1 or fmv > 30:
            continue

        # Sleeper score: high VORP + budget pressure + price discount
        sleeper_score = (
            ps.vorp * 0.4
            + constraint_ratio * 20
            + (1 - fmv / 30) * 10
        )

        # Estimate what they'll actually go for
        estimated_price = max(1, min(5, int(fmv * (1 - constraint_ratio * 0.7))))

        candidates.append({
            "player_name": ps.projection.player_name,
            "position": ps.projection.position.value,
            "vorp": round(ps.vorp, 1),
            "fmv": round(fmv, 1),
            "tier": ps.projection.tier,
            "estimated_price": estimated_price,
            "sleeper_score": round(sleeper_score, 1),
        })

    candidates.sort(key=lambda c: c["sleeper_score"], reverse=True)
    return candidates[:max_results]
