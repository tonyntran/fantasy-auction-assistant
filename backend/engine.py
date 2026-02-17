"""
Calculation engine — pure-math functions for VORP, FMV, inflation, scarcity, and advice.
All functions are stateless (take explicit parameters) for testability.
"""

from models import PlayerState, EngineAdvice, AdviceAction, MyTeamState
from state import DraftState
from config import settings
from adp import compare_fmv_to_adp


def calculate_vorp(player: PlayerState) -> float:
    """Return the player's pre-computed VORP."""
    return player.vorp


def calculate_vona(player: PlayerState, state: DraftState) -> tuple[float, str | None]:
    """
    Value Over Next Available — how much better is this player than
    the next-best undrafted player at the same position.
    Returns (vona_value, next_player_name).
    """
    pos = player.projection.position.value
    remaining = state.get_remaining_players(pos)  # sorted by VORP desc

    found = False
    for ps in remaining:
        if ps.projection.player_name == player.projection.player_name:
            found = True
            continue
        if found:
            vona = player.projection.projected_points - ps.projection.projected_points
            return (round(max(0.0, vona), 1), ps.projection.player_name)

    # Last at position — VONA equals their VORP (no next alternative)
    return (round(max(0.0, player.vorp), 1), None)


def calculate_fmv(player: PlayerState, state: DraftState) -> float:
    """
    Fair Market Value adjusted by live inflation.
    FMV = BaselineAAV * inflation_factor
    """
    base = player.projection.baseline_aav
    inflation = state.get_inflation_factor()
    return round(base * inflation, 1)


def calculate_inflation(state: DraftState) -> float:
    """
    Inflation = total_remaining_cash / total_remaining_AAV.
    > 1.0 means money is plentiful (prices inflate).
    < 1.0 means money is tight (bargains ahead).
    """
    return state.get_inflation_factor()


def calculate_scarcity_multiplier(player: PlayerState, state: DraftState) -> float:
    """
    Positional scarcity premium based on position+tier group.
    If 70%+ of a tier is drafted, remaining players in that tier gain value.
    """
    pos = player.projection.position.value
    tier = player.projection.tier

    same_group = [
        ps
        for ps in state.players.values()
        if ps.projection.position.value == pos and ps.projection.tier == tier
    ]

    if not same_group:
        return 1.0

    drafted_count = sum(1 for ps in same_group if ps.is_drafted)
    drafted_pct = drafted_count / len(same_group)

    if drafted_pct >= 0.85:
        return 1.30
    elif drafted_pct >= 0.70:
        return 1.15
    elif drafted_pct >= 0.50:
        return 1.05
    else:
        return 1.0


def calculate_need_multiplier(player: PlayerState, state: DraftState) -> float:
    """
    Roster need multiplier based on how many open slots can accept this position.

    Returns:
      0.0  — No open slot exists for this position. Hard PASS.
      0.5  — Only flex slots remain (position starters full). Discount value.
      1.0  — Dedicated starter slot still open. Full value.
      1.2  — Last open slot for this position AND it's a need. Slight premium.
    """
    pos = player.projection.position.value
    eligibility = settings.SLOT_ELIGIBILITY
    my_team = state.my_team

    open_slots = my_team.open_slots_for_position(pos, eligibility)

    if not open_slots:
        return 0.0  # Cannot roster this player at all

    # Check if any dedicated (non-flex) slot is still open for this position
    has_dedicated_slot = False
    flex_only = True
    for slot_label in open_slots:
        base_type = my_team.slot_types.get(slot_label, slot_label.rstrip("0123456789"))
        if base_type == pos:
            has_dedicated_slot = True
            flex_only = False
            break
        if base_type not in ("FLEX", "SUPERFLEX"):
            flex_only = False

    if flex_only:
        # Only flex spots remain — still usable but discount since flex is versatile
        return 0.5

    # Dedicated slot open — check if it's the last one (urgency premium)
    dedicated_open = sum(
        1 for sl in open_slots
        if my_team.slot_types.get(sl, sl.rstrip("0123456789")) == pos
    )
    if dedicated_open == 1 and has_dedicated_slot:
        return 1.2  # Last dedicated slot — slight urgency premium

    return 1.0


def calculate_strategy_multiplier(player: PlayerState, state: DraftState) -> float:
    """
    Strategy-based multiplier combining position and tier weights
    from the active draft strategy profile.
    """
    strategy = settings.active_strategy
    pos = player.projection.position.value
    tier = player.projection.tier
    pos_w = strategy["position_weights"].get(pos, 1.0)
    tier_w = strategy["tier_weights"].get(tier, 1.0)
    return round(pos_w * tier_w, 3)


def calculate_max_bid(my_team: MyTeamState) -> int:
    """Maximum affordable bid = budget - ($1 * remaining empty slots after this pick)."""
    return my_team.max_bid


def get_engine_advice(
    player_name: str,
    current_bid: float,
    state: DraftState,
) -> EngineAdvice:
    """
    Pure-math recommendation combining VORP, FMV, scarcity, roster need,
    and budget constraints.
    """
    player = state.get_player(player_name)

    # Player not in our projections — conservative PASS
    if player is None:
        return EngineAdvice(
            action=AdviceAction.PASS,
            max_bid=0,
            fmv=0.0,
            inflation_rate=state.get_inflation_factor(),
            scarcity_multiplier=1.0,
            vorp=0.0,
            reasoning=f"'{player_name}' not found in projections. PASS recommended.",
        )

    vorp = calculate_vorp(player)
    vona_value, vona_next = calculate_vona(player, state)
    fmv = calculate_fmv(player, state)
    scarcity = calculate_scarcity_multiplier(player, state)
    need = calculate_need_multiplier(player, state)
    inflation = calculate_inflation(state)
    strat_mult = calculate_strategy_multiplier(player, state)
    adjusted_fmv = round(fmv * scarcity * need * strat_mult, 1)
    budget_max = calculate_max_bid(state.my_team)
    pos = player.projection.position.value

    # Hard constraint: no roster slot available
    if need == 0.0:
        return EngineAdvice(
            action=AdviceAction.PASS,
            max_bid=0,
            fmv=round(fmv * scarcity, 1),  # Show the "true" FMV without need discount
            inflation_rate=inflation,
            scarcity_multiplier=scarcity,
            vorp=vorp,
            reasoning=(
                f"No open roster slot for {pos}. All {pos}-eligible spots are filled. "
                f"PASS — cannot roster this player."
            ),
        )

    # Build need context for reasoning
    need_info = ""
    if need == 0.5:
        need_info = f" [Only FLEX slots open for {pos} — value discounted 50%.]"
    elif need == 1.2:
        need_info = f" [Last dedicated {pos} slot — slight urgency premium.]"

    # Strategy context for reasoning
    strat_info = ""
    if strat_mult != 1.0:
        strat_info = f" [Strategy x{strat_mult:.2f}]"

    # Decision logic
    effective_max = min(int(adjusted_fmv), budget_max)

    if current_bid <= 0:
        # No active bid yet — provide valuation
        action = AdviceAction.BUY if vorp > 0 else AdviceAction.PASS
        reasoning = (
            f"FMV: ${adjusted_fmv} (base ${fmv}, scarcity x{scarcity:.2f}, need x{need:.1f}). "
            f"VORP: {vorp:.1f}. Budget max: ${budget_max}.{need_info}{strat_info}"
        )
    elif current_bid > adjusted_fmv * 1.15:
        # Well above value — let it go
        action = AdviceAction.PASS
        overpay_pct = (current_bid / adjusted_fmv - 1) * 100 if adjusted_fmv > 0 else 100
        reasoning = (
            f"Current bid ${int(current_bid)} exceeds adjusted FMV "
            f"${adjusted_fmv} by {overpay_pct:.0f}%. Let someone else overpay.{need_info}{strat_info}"
        )
    elif current_bid > adjusted_fmv:
        # Slightly over FMV — price enforce
        action = AdviceAction.PRICE_ENFORCE
        effective_max = min(int(adjusted_fmv * 1.10), budget_max)
        reasoning = (
            f"Bid ${int(current_bid)} is above FMV ${adjusted_fmv} but close. "
            f"Push price to make the winner overpay. Don't exceed ${effective_max}.{need_info}{strat_info}"
        )
    elif vorp > 0:
        # At or below value with positive VORP — buy
        action = AdviceAction.BUY
        reasoning = (
            f"${int(current_bid)} is at or below adjusted FMV ${adjusted_fmv} "
            f"(base ${fmv}, scarcity x{scarcity:.2f}, need x{need:.1f}). "
            f"VORP: {vorp:.1f}. BUY up to ${effective_max}.{need_info}{strat_info}"
        )
    else:
        # No VORP value
        action = AdviceAction.PASS
        reasoning = f"Low VORP ({vorp:.1f}). Not worth pursuing at any price.{need_info}{strat_info}"

    # VONA context
    if vona_next:
        reasoning += f" VONA: {vona_value:.1f} pts over {vona_next} at {pos}."
    elif vona_value > 0:
        reasoning += f" VONA: {vona_value:.1f} (last available at {pos})."

    # ADP comparison
    adp_val = player.adp_value
    adp_note = compare_fmv_to_adp(adjusted_fmv, adp_val)
    if adp_note:
        reasoning += f" [{adp_note}]"

    # Opponent demand (if opponent tracker is available)
    demand = None
    if hasattr(state, "opponent_tracker") and state.opponent_tracker:
        remaining_at_pos = len(state.get_remaining_players(pos))
        demand = state.opponent_tracker.get_position_demand(pos, remaining_at_pos)
        if demand and demand.get("bidding_war_risk"):
            reasoning += f" ⚠ Bidding war likely: {demand['teams_needing']} teams need {pos} with {demand['players_remaining']} left."

    return EngineAdvice(
        action=action,
        max_bid=effective_max,
        fmv=adjusted_fmv,
        inflation_rate=inflation,
        scarcity_multiplier=scarcity,
        vorp=vorp,
        reasoning=reasoning,
        vona=vona_value,
        vona_next_player=vona_next,
        adp_value=adp_val,
        adp_vs_fmv=adp_note,
        opponent_demand=demand,
        strategy_multiplier=strat_mult,
    )
