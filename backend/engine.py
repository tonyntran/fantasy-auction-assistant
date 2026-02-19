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
    Roster need multiplier: 1.0 if a starter slot can accept this position,
    0.0 if only bench or no slots available. BENCH slots don't drive bidding.
    """
    pos = player.projection.position.value
    eligibility = settings.SLOT_ELIGIBILITY
    open_slots = state.my_team.open_slots_for_position(pos, eligibility)
    if not open_slots:
        return 0.0
    # Only count starter (non-BENCH) slots
    starter_slots = [
        s for s in open_slots
        if state.my_team.slot_types.get(s, s.rstrip("0123456789")) != "BENCH"
    ]
    return 1.0 if starter_slots else 0.0


def _has_only_bench_slots(player: PlayerState, state: DraftState) -> bool:
    """Check if the only open slots for this player's position are BENCH."""
    pos = player.projection.position.value
    eligibility = settings.SLOT_ELIGIBILITY
    open_slots = state.my_team.open_slots_for_position(pos, eligibility)
    if not open_slots:
        return False
    return all(
        state.my_team.slot_types.get(s, s.rstrip("0123456789")) == "BENCH"
        for s in open_slots
    )


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
    bench_only = _has_only_bench_slots(player, state)
    inflation = calculate_inflation(state)
    strat_mult = calculate_strategy_multiplier(player, state)
    adjusted_fmv = round(fmv * scarcity * need * strat_mult, 1)
    # Market FMV: what the player is worth on the open market (ignoring our roster need)
    market_fmv = round(fmv * scarcity * strat_mult, 1)
    budget_max = calculate_max_bid(state.my_team)
    pos = player.projection.position.value

    # Build need context for reasoning
    need_info = ""
    if need == 0.0 and bench_only:
        need_info = f" [Only bench slots open for {pos}.]"
    elif need == 0.0:
        need_info = f" [No open {pos} slot.]"

    # Strategy context for reasoning
    strat_info = ""
    if strat_mult != 1.0:
        strat_info = f" [Strategy x{strat_mult:.2f}]"

    # Decision logic
    effective_max = min(int(adjusted_fmv), budget_max)
    # Always display market FMV (what the player is worth on the open market)
    # Need multiplier affects max_bid logic but shouldn't distort the FMV display
    display_fmv = market_fmv

    if need == 0.0 and current_bid > 0 and vorp > 0 and current_bid < market_fmv:
        # No starter slot, but player going below market value — price enforce
        action = AdviceAction.PRICE_ENFORCE
        effective_max = min(int(market_fmv), budget_max)
        slot_context = "Only bench slots" if bench_only else "No open slot"
        reasoning = (
            f"{slot_context} for {pos}, but ${int(current_bid)} is below market FMV "
            f"${market_fmv}. Bid up to ${effective_max} to deny a bargain "
            f"and drain opponent budgets.{strat_info}"
        )
    elif need == 0.0 and bench_only:
        # Only bench slots — don't actively pursue, fill at $1 later
        action = AdviceAction.PASS
        effective_max = 0
        reasoning = (
            f"All starter slots for {pos} are filled — only bench spots remain. "
            f"PASS — fill bench at $1 later."
        )
    elif need == 0.0:
        # No roster slot at all
        action = AdviceAction.PASS
        effective_max = 0
        reasoning = (
            f"No open roster slot for {pos}. All {pos}-eligible spots are filled. "
            f"PASS — cannot roster this player."
        )
    elif current_bid <= 0:
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
    elif current_bid > adjusted_fmv and vorp > 0:
        # Slightly over FMV but you need the player — cautious BUY
        action = AdviceAction.BUY
        effective_max = min(int(adjusted_fmv * 1.10), budget_max)
        overpay_pct = (current_bid / adjusted_fmv - 1) * 100 if adjusted_fmv > 0 else 0
        reasoning = (
            f"Bid ${int(current_bid)} is {overpay_pct:.0f}% above FMV ${adjusted_fmv}. "
            f"Slightly over value — proceed only if you value the {pos} need. "
            f"Max ${effective_max}.{need_info}{strat_info}"
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
    adp_note = compare_fmv_to_adp(display_fmv, adp_val)
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
        fmv=display_fmv,
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
