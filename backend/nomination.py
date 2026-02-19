"""
Nomination strategy engine — suggests who to nominate when it's your turn.

Strategies:
  BUDGET_DRAIN:       Target rich opponents — nominate expensive players THEY need
  RIVAL_DESPERATION:  Nominate scarce positions to start bidding wars between rivals
  POISON_PILL:        Nominate players that 2+ desperate rivals both need
  BARGAIN_SNAG:       Cheap players you need that opponents DON'T — snag quietly
  TIMING:             Nominate drain picks early, bargains late based on draft phase
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import DraftState

from engine import calculate_fmv, calculate_scarcity_multiplier
from config import settings


def _get_opponent_needs_by_team(state: "DraftState") -> dict[str, set[str]]:
    """Return {team_id: set of positions the team still needs starters at}."""
    tracker = state.opponent_tracker
    if not tracker or not tracker.team_rosters:
        return {}
    needs: dict[str, set[str]] = {}
    for team_id, pos_counts in tracker.team_rosters.items():
        team_needs = set()
        for pos in settings.display_positions:
            max_slots = tracker._max_slots_for_position(pos)
            filled = pos_counts.get(pos, 0)
            if filled < max_slots:
                team_needs.add(pos)
        needs[team_id] = team_needs
    return needs


def _teams_needing_position(opponent_needs: dict[str, set[str]], pos: str) -> int:
    """Count how many opponent teams still need this position."""
    return sum(1 for needs in opponent_needs.values() if pos in needs)


def _get_rich_teams(state: "DraftState", top_n: int = 3) -> list[dict]:
    """Return the top N opponent teams by spending power."""
    tracker = state.opponent_tracker
    if not tracker:
        return []
    threats = tracker.get_team_threat_levels()
    return threats[:top_n]


def _get_draft_phase(state: "DraftState") -> str:
    """Detect draft phase based on % of players drafted.
    Elite (0-15%), Middle (15-50%), Value (50-80%), Dollar (80%+)."""
    total = len(state.players)
    drafted = sum(1 for ps in state.players.values() if ps.is_drafted)
    if total == 0:
        return "elite"
    pct = drafted / total * 100
    if pct < 15:
        return "elite"
    elif pct < 50:
        return "middle"
    elif pct < 80:
        return "value"
    return "dollar"


def get_nomination_suggestions(state: "DraftState", top_n: int = 5) -> list[dict]:
    """Generate ranked nomination suggestions with strategy reasoning."""
    remaining = state.get_remaining_players()
    my_needs = state.get_positional_need()
    opponent_needs = _get_opponent_needs_by_team(state)
    rich_teams = _get_rich_teams(state)
    phase = _get_draft_phase(state)

    # Rich team IDs and what they need
    rich_team_needs: dict[str, set[str]] = {}
    for t in rich_teams:
        tid = t["team_id"]
        rich_team_needs[tid] = opponent_needs.get(tid, set())

    suggestions = []

    for ps in remaining:
        pos = ps.projection.position.value
        fmv = calculate_fmv(ps, state)
        scarcity = calculate_scarcity_multiplier(ps, state)
        my_need_count = my_needs.get(pos, 0)
        opp_teams_needing = _teams_needing_position(opponent_needs, pos)

        # --- Strategy A: Targeted Budget Drain ---
        # Nominate expensive players that RICH teams specifically need
        if my_need_count == 0 and fmv > 15:
            rich_targets = [
                tid for tid, needs in rich_team_needs.items() if pos in needs
            ]
            if rich_targets:
                tracker = state.opponent_tracker
                team_names = [tracker.team_names.get(tid, tid) for tid in rich_targets[:2]]
                suggestions.append({
                    "player_name": ps.projection.player_name,
                    "position": pos,
                    "fmv": round(fmv, 1),
                    "strategy": "BUDGET_DRAIN",
                    "reasoning": f"Forces {', '.join(team_names)} to spend ${fmv:.0f}+. You don't need {pos}.",
                    "priority": round(fmv * (1 + len(rich_targets) * 0.2), 1),
                })

        # --- Strategy B: Rival Desperation ---
        # High scarcity positions you've filled — start bidding wars
        if scarcity >= 1.15 and my_need_count == 0:
            demand_info = ""
            if state.opponent_tracker:
                remaining_at_pos = len(state.get_remaining_players(pos))
                demand = state.opponent_tracker.get_position_demand(pos, remaining_at_pos)
                if demand.get("bidding_war_risk"):
                    demand_info = f" {demand['teams_needing']} teams fighting over {demand['players_remaining']} left."
            suggestions.append({
                "player_name": ps.projection.player_name,
                "position": pos,
                "fmv": round(fmv, 1),
                "strategy": "RIVAL_DESPERATION",
                "reasoning": f"{pos} scarcity {scarcity:.2f}x — rivals will overpay.{demand_info}",
                "priority": round(fmv * scarcity * (1 + opp_teams_needing * 0.1), 1),
            })

        # --- Strategy C: Poison Pill ---
        # Player that 2+ rival teams desperately need — force them to bid each other up
        if my_need_count == 0 and opp_teams_needing >= 2 and fmv > 10:
            remaining_at_pos = len(state.get_remaining_players(pos))
            ratio = opp_teams_needing / max(remaining_at_pos, 1)
            if ratio >= 0.5:  # More teams than supply
                suggestions.append({
                    "player_name": ps.projection.player_name,
                    "position": pos,
                    "fmv": round(fmv, 1),
                    "strategy": "POISON_PILL",
                    "reasoning": f"{opp_teams_needing} teams need {pos} with only {remaining_at_pos} left — bidding war guaranteed.",
                    "priority": round(fmv * ratio * 2, 1),
                })

        # --- Strategy D: Bargain Snag ---
        # Dynamic threshold: early = top 25% of FMV range, late = bottom 50%
        # Only suggest players opponents DON'T need (stealth picks)
        if my_need_count > 0 and ps.vorp > 0:
            bargain_threshold = {
                "elite": 0.15,   # Only very cheap relative to pool
                "middle": 0.25,  # Moderate bargains
                "value": 0.40,   # Wider range
                "dollar": 0.60,  # Most remaining are bargain territory
            }.get(phase, 0.25)

            # Get max FMV at this position for relative threshold
            pos_remaining = state.get_remaining_players(pos)
            max_pos_fmv = calculate_fmv(pos_remaining[0], state) if pos_remaining else fmv
            threshold_fmv = max_pos_fmv * bargain_threshold

            if fmv <= threshold_fmv:
                # Stealth bonus: fewer opponents need this position = quieter nomination
                stealth = max(0, 5 - opp_teams_needing)
                suggestions.append({
                    "player_name": ps.projection.player_name,
                    "position": pos,
                    "fmv": round(fmv, 1),
                    "strategy": "BARGAIN_SNAG",
                    "reasoning": f"You need {pos}. FMV ${fmv:.0f} is {round(fmv/max_pos_fmv*100)}% of top — "
                                 f"{'low opponent interest' if opp_teams_needing <= 1 else f'{opp_teams_needing} teams also need {pos}'}.",
                    "priority": round(ps.vorp * (1 + stealth * 0.2), 1),
                })

    # --- Improvement 5: Timing adjustments ---
    # Early draft: boost drain/desperation/poison (force spending)
    # Late draft: boost bargain (grab value quietly)
    phase_boosts = {
        "elite":  {"BUDGET_DRAIN": 1.3, "RIVAL_DESPERATION": 1.2, "POISON_PILL": 1.3, "BARGAIN_SNAG": 0.7},
        "middle": {"BUDGET_DRAIN": 1.1, "RIVAL_DESPERATION": 1.1, "POISON_PILL": 1.2, "BARGAIN_SNAG": 1.0},
        "value":  {"BUDGET_DRAIN": 0.8, "RIVAL_DESPERATION": 1.0, "POISON_PILL": 1.1, "BARGAIN_SNAG": 1.3},
        "dollar": {"BUDGET_DRAIN": 0.5, "RIVAL_DESPERATION": 0.7, "POISON_PILL": 0.8, "BARGAIN_SNAG": 1.5},
    }
    boosts = phase_boosts.get(phase, {})

    # Apply strategy-based priority adjustments
    active = settings.active_strategy
    for s in suggestions:
        pos = s["position"]
        pos_weight = active["position_weights"].get(pos, 1.0)

        # Strategy weight from active profile
        if s["strategy"] in ("BUDGET_DRAIN", "RIVAL_DESPERATION", "POISON_PILL"):
            s["priority"] *= (2.0 - pos_weight)
        elif s["strategy"] == "BARGAIN_SNAG":
            s["priority"] *= pos_weight

        # Phase timing boost
        s["priority"] *= boosts.get(s["strategy"], 1.0)
        s["priority"] = round(s["priority"], 1)

    # Deduplicate: keep highest-priority entry per player
    seen = {}
    for s in suggestions:
        name = s["player_name"]
        if name not in seen or s["priority"] > seen[name]["priority"]:
            seen[name] = s

    result = sorted(seen.values(), key=lambda s: s["priority"], reverse=True)
    return result[:top_n]
