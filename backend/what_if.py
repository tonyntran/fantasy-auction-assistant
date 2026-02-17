"""
What-If simulation — "What if I spend $X on PlayerY?"

Creates a deep copy of draft state, simulates the purchase,
then greedily fills remaining roster by best VORP/$ ratio.
"""

import copy
from typing import Optional

from state import DraftState
from engine import calculate_fmv, calculate_strategy_multiplier
from config import settings


def clone_state(state: DraftState) -> DraftState:
    """Create a deep copy of DraftState bypassing the singleton."""
    clone = object.__new__(DraftState)
    clone._initialized = True
    clone.players = copy.deepcopy(state.players)
    clone.team_budgets = copy.deepcopy(state.team_budgets)
    clone.my_team = state.my_team.model_copy(deep=True)
    clone.replacement_level = dict(state.replacement_level)
    clone.total_remaining_aav = state.total_remaining_aav
    clone.total_remaining_cash = state.total_remaining_cash
    clone.inflation_factor = state.inflation_factor
    clone.draft_log = list(state.draft_log)
    clone.raw_latest = dict(state.raw_latest)
    clone.inflation_history = list(state.inflation_history)
    clone.name_resolver = state.name_resolver  # Share (read-only)
    clone.newly_drafted = []
    clone.dead_money_log = []
    clone.team_aliases = dict(state.team_aliases)
    clone.resolved_sport = state.resolved_sport
    # Give it a dummy opponent_tracker
    from opponent_model import OpponentTracker
    clone.opponent_tracker = OpponentTracker()
    return clone


def simulate_what_if(player_name: str, price: int, state: DraftState) -> dict:
    """
    Simulate purchasing a player and show optimal remaining draft.

    1. Clone state
    2. Apply the hypothetical purchase
    3. Greedily fill remaining roster by best VORP/$ ratio
    4. Return analysis
    """
    # Verify player exists
    player = state.get_player(player_name)
    if not player:
        return {"error": f"'{player_name}' not found in projections."}
    if player.is_drafted:
        return {"error": f"{player.projection.player_name} is already drafted."}

    actual_name = player.projection.player_name
    pos = player.projection.position.value

    # Clone and simulate
    sim = clone_state(state)

    # Find the player in the clone
    sim_player = sim.get_player(player_name)
    if not sim_player:
        return {"error": "Clone error — player not found in simulation."}

    # Apply purchase
    sim_player.is_drafted = True
    sim_player.draft_price = price
    sim_player.drafted_by_team = settings.my_team_name
    sim.my_team.budget -= price

    # Slot into roster
    open_slots = sim.my_team.open_slots_for_position(pos, settings.SLOT_ELIGIBILITY)
    if open_slots:
        # Prefer dedicated slot
        best_slot = None
        for slot in open_slots:
            base_type = sim.my_team.slot_types.get(slot, slot.rstrip("0123456789"))
            if base_type == pos:
                best_slot = slot
                break
        if best_slot is None:
            best_slot = open_slots[0]
        sim.my_team.roster[best_slot] = actual_name
        sim.my_team.players_acquired.append({"name": actual_name, "position": pos, "price": price})

    sim._recompute_aggregates()

    # Greedy optimal fill of remaining slots
    optimal_picks = []
    remaining_budget = sim.my_team.budget
    needs = sim.get_positional_need()

    for _ in range(settings.roster_size):  # Safety bound
        if remaining_budget <= 0:
            break
        if not any(v > 0 for v in needs.values()):
            break

        best = None
        best_ratio = -1

        for ps in sim.get_remaining_players():
            p_pos = ps.projection.position.value
            if needs.get(p_pos, 0) <= 0:
                continue
            fmv = calculate_fmv(ps, sim)
            pick_cost = max(1, int(fmv * 0.8))
            if pick_cost > remaining_budget:
                continue
            strategy_mult = calculate_strategy_multiplier(ps, sim)
            ratio = (ps.vorp * strategy_mult) / max(pick_cost, 1)
            if ratio > best_ratio:
                best_ratio = ratio
                best = (ps, pick_cost)

        if not best:
            break

        ps, pick_cost = best
        p_pos = ps.projection.position.value
        optimal_picks.append({
            "player": ps.projection.player_name,
            "position": p_pos,
            "estimated_price": pick_cost,
            "vorp": round(ps.vorp, 1),
        })
        ps.is_drafted = True
        remaining_budget -= pick_cost
        needs[p_pos] = needs.get(p_pos, 0) - 1

    # Calculate projected total
    projected_total = sum(
        sim.get_player(p["name"]).projection.projected_points
        for p in sim.my_team.players_acquired
        if sim.get_player(p["name"])
    )
    projected_total += sum(
        state.get_player(p["player"]).projection.projected_points
        for p in optimal_picks
        if state.get_player(p["player"])
    )

    return {
        "hypothetical_purchase": {"player": actual_name, "price": price},
        "remaining_budget_after": sim.my_team.budget,
        "optimal_remaining_picks": optimal_picks,
        "projected_total_points": round(projected_total, 1),
        "roster_completeness": f"{len(sim.my_team.players_acquired) + len(optimal_picks)}/{settings.roster_size}",
    }
