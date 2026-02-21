"""
Tests for engine.py: VORP, FMV, VONA, scarcity, need, strategy multipliers, and full advice.
"""

import pytest
from models import (
    PlayerProjection,
    PlayerState,
    Position,
    AdviceAction,
)
from engine import (
    calculate_vorp,
    calculate_fmv,
    calculate_vona,
    calculate_scarcity_multiplier,
    calculate_need_multiplier,
    calculate_strategy_multiplier,
    get_engine_advice,
)
from state import DraftState
from models import DraftUpdate


# =====================================================================
# calculate_vorp
# =====================================================================

class TestCalculateVorp:
    def test_returns_player_vorp(self, draft_state):
        ps = draft_state.players["patrick mahomes"]
        assert calculate_vorp(ps) == ps.vorp

    def test_vorp_is_non_negative(self, draft_state):
        for ps in draft_state.players.values():
            assert calculate_vorp(ps) >= 0.0

    def test_best_player_has_highest_vorp(self, draft_state):
        """At each position, the top-projected player should have higher or equal VORP."""
        qbs = [ps for ps in draft_state.players.values() if ps.projection.position == Position.QB]
        sorted_by_pts = sorted(qbs, key=lambda p: p.projection.projected_points, reverse=True)
        sorted_by_vorp = sorted(qbs, key=lambda p: p.vorp, reverse=True)
        # Top by points should also be top by VORP
        assert sorted_by_pts[0].projection.player_name == sorted_by_vorp[0].projection.player_name

    def test_zero_vorp_for_replacement_level(self, draft_state):
        """Players at or near replacement level should have ~0 VORP."""
        # K and DEF have baseline_rank=1, with only 1 player each in our sample
        # They're effectively AT replacement level
        k_ps = draft_state.players["tyler bass"]
        # VORP could be 0 or very small since there's only one K
        assert k_ps.vorp >= 0.0


# =====================================================================
# calculate_fmv
# =====================================================================

class TestCalculateFmv:
    def test_fmv_applies_inflation(self, draft_state):
        ps = draft_state.players["patrick mahomes"]
        fmv = calculate_fmv(ps, draft_state)
        expected = round(ps.projection.baseline_aav * draft_state.get_inflation_factor(), 1)
        assert fmv == expected

    def test_fmv_changes_with_inflation(self, draft_state):
        ps = draft_state.players["saquon barkley"]
        fmv_before = calculate_fmv(ps, draft_state)

        # Simulate inflation by changing team budgets
        draft_state.team_budgets = {"T1": 200, "T2": 200, "T3": 200}
        draft_state._recompute_aggregates()
        fmv_after = calculate_fmv(ps, draft_state)

        # With less total cash (600 instead of 2000), inflation factor drops,
        # and FMV should decrease
        assert fmv_after < fmv_before

    def test_fmv_zero_baseline(self, draft_state):
        """Player with 0 baseline_aav should have 0 FMV."""
        proj = PlayerProjection(
            player_name="Zero AAV",
            position=Position.K,
            projected_points=50.0,
            baseline_aav=0.0,
            tier=5,
        )
        ps = PlayerState(projection=proj, vorp=0.0)
        fmv = calculate_fmv(ps, draft_state)
        assert fmv == 0.0


# =====================================================================
# calculate_vona
# =====================================================================

class TestCalculateVona:
    def test_vona_for_top_player(self, draft_state):
        """Top QB should have positive VONA over the next QB."""
        ps = draft_state.players["patrick mahomes"]
        vona, next_name = calculate_vona(ps, draft_state)
        assert vona >= 0.0
        assert next_name is not None  # Should be Josh Allen or another QB

    def test_vona_next_player_name(self, draft_state):
        """VONA should report the correct next player."""
        ps = draft_state.players["patrick mahomes"]
        _, next_name = calculate_vona(ps, draft_state)
        # Mahomes (380) -> next is Allen (370) -> VONA = 10
        assert next_name == "Josh Allen"

    def test_vona_value_is_correct(self, draft_state):
        ps = draft_state.players["patrick mahomes"]
        vona, _ = calculate_vona(ps, draft_state)
        # Mahomes 380 - Allen 370 = 10
        assert vona == 10.0

    def test_vona_last_at_position(self, draft_state):
        """The last player at a position should have VONA equal to their VORP."""
        ps = draft_state.players["tyler bass"]
        vona, next_name = calculate_vona(ps, draft_state)
        # Only one K in the sample, so they're last at position
        assert next_name is None
        assert vona == round(max(0.0, ps.vorp), 1)

    def test_vona_after_drafting(self, draft_state, sample_draft_update):
        """After drafting the top QB, the next QB's VONA should change."""
        # Draft Mahomes
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        ps_allen = draft_state.players["josh allen"]
        vona, next_name = calculate_vona(ps_allen, draft_state)
        # Allen (370) -> Hurts (340) = 30
        assert vona == 30.0
        assert next_name == "Jalen Hurts"

    def test_vona_with_no_remaining(self, draft_state):
        """If all players at a position are drafted except one, that one has VONA = VORP."""
        # Draft all QBs except Mahomes
        for name in ["josh allen", "jalen hurts", "lamar jackson"]:
            draft_state.players[name].is_drafted = True
        draft_state._recompute_aggregates()

        ps = draft_state.players["patrick mahomes"]
        vona, next_name = calculate_vona(ps, draft_state)
        assert next_name is None
        assert vona == round(max(0.0, ps.vorp), 1)


# =====================================================================
# calculate_scarcity_multiplier
# =====================================================================

class TestCalculateScarcityMultiplier:
    def test_no_scarcity_initially(self, draft_state):
        """With no players drafted, scarcity should be 1.0."""
        ps = draft_state.players["saquon barkley"]
        mult = calculate_scarcity_multiplier(ps, draft_state)
        assert mult == 1.0

    def test_scarcity_at_50_percent(self, draft_state):
        """When 50% of a position+tier group is drafted, scarcity is 1.05."""
        # We have 3 tier-1 RBs (Barkley, Hall, Robinson)
        # Draft 2 of 3 = 66% -> actually >= 50% but < 70% -> 1.05
        draft_state.players["breece hall"].is_drafted = True
        draft_state.players["bijan robinson"].is_drafted = True
        ps = draft_state.players["saquon barkley"]
        mult = calculate_scarcity_multiplier(ps, draft_state)
        assert mult == 1.05

    def test_scarcity_small_group_50_pct(self, draft_state):
        """With a 2-player tier group, drafting 1 of 2 = 50% -> 1.05."""
        # Tier-1 WRs: CeeDee Lamb, Ja'Marr Chase (2 players)
        draft_state.players["ceedee lamb"].is_drafted = True
        # 1/2 = 50% -> 1.05
        ps = draft_state.players["jamarr chase"]
        mult = calculate_scarcity_multiplier(ps, draft_state)
        assert mult == 1.05

    def test_scarcity_single_player_group(self, draft_state):
        """A tier group with 1 player (0 drafted) should have scarcity 1.0."""
        # Tier-1 TEs: only Travis Kelce (1 player)
        ps = draft_state.players["travis kelce"]
        mult = calculate_scarcity_multiplier(ps, draft_state)
        assert mult == 1.0

    def test_scarcity_multiplier_values(self, draft_state):
        """Test all scarcity thresholds with a controlled group."""
        from models import PlayerProjection, PlayerState, Position

        # Create a controlled group of 10 players at same position+tier
        for i in range(10):
            name = f"test_rb_{i}"
            proj = PlayerProjection(
                player_name=f"TestRB{i}",
                position=Position.RB,
                projected_points=100.0 + i,
                baseline_aav=10.0,
                tier=99,
            )
            draft_state.players[name] = PlayerState(projection=proj, vorp=10.0)

        target = draft_state.players["test_rb_0"]

        # 0/10 drafted = 0% -> 1.0
        assert calculate_scarcity_multiplier(target, draft_state) == 1.0

        # Draft 5/10 = 50% -> 1.05
        for i in range(1, 6):
            draft_state.players[f"test_rb_{i}"].is_drafted = True
        assert calculate_scarcity_multiplier(target, draft_state) == 1.05

        # Draft 7/10 = 70% -> 1.15
        for i in range(6, 8):
            draft_state.players[f"test_rb_{i}"].is_drafted = True
        assert calculate_scarcity_multiplier(target, draft_state) == 1.15

        # Draft 9/10 = 90% -> 1.30
        for i in range(8, 10):
            draft_state.players[f"test_rb_{i}"].is_drafted = True
        assert calculate_scarcity_multiplier(target, draft_state) == 1.30


# =====================================================================
# calculate_need_multiplier
# =====================================================================

class TestCalculateNeedMultiplier:
    def test_need_with_open_slot(self, draft_state):
        """Should return 1.0 when starter slot is available."""
        ps = draft_state.players["patrick mahomes"]
        mult = calculate_need_multiplier(ps, draft_state)
        assert mult == 1.0

    def test_need_no_slot_available(self, draft_state):
        """Should return 0.0 when no slots can accept the position."""
        ps = draft_state.players["patrick mahomes"]
        # Fill the QB slot
        draft_state.my_team.roster["QB"] = "Some QB"
        mult = calculate_need_multiplier(ps, draft_state)
        assert mult == 0.0

    def test_need_with_flex_available(self, draft_state):
        """RB should still have 1.0 need if FLEX slots are open even after RB slots full."""
        # Fill RB1 and RB2
        draft_state.my_team.roster["RB1"] = "Player A"
        draft_state.my_team.roster["RB2"] = "Player B"
        ps = draft_state.players["bijan robinson"]
        mult = calculate_need_multiplier(ps, draft_state)
        assert mult == 1.0  # FLEX slots still open

    def test_need_zero_when_all_eligible_slots_full(self, draft_state):
        """When RB, and all FLEX slots are full, RB need = 0."""
        draft_state.my_team.roster["RB1"] = "Player A"
        draft_state.my_team.roster["RB2"] = "Player B"
        draft_state.my_team.roster["FLEX1"] = "Player C"
        draft_state.my_team.roster["FLEX2"] = "Player D"
        ps = draft_state.players["bijan robinson"]
        mult = calculate_need_multiplier(ps, draft_state)
        assert mult == 0.0


# =====================================================================
# calculate_strategy_multiplier
# =====================================================================

class TestCalculateStrategyMultiplier:
    def test_balanced_is_1_0(self, draft_state, _test_settings):
        """Balanced strategy should return 1.0 for all players."""
        _test_settings.draft_strategy = "balanced"
        ps = draft_state.players["patrick mahomes"]
        mult = calculate_strategy_multiplier(ps, draft_state)
        assert mult == 1.0

    def test_rb_heavy_boosts_rb(self, draft_state, _test_settings):
        _test_settings.draft_strategy = "rb_heavy"
        ps = draft_state.players["saquon barkley"]
        mult = calculate_strategy_multiplier(ps, draft_state)
        assert mult > 1.0

    def test_rb_heavy_discounts_qb(self, draft_state, _test_settings):
        _test_settings.draft_strategy = "rb_heavy"
        ps = draft_state.players["patrick mahomes"]
        mult = calculate_strategy_multiplier(ps, draft_state)
        assert mult < 1.0

    def test_studs_and_steals_boosts_tier1(self, draft_state, _test_settings):
        _test_settings.draft_strategy = "studs_and_steals"
        ps = draft_state.players["patrick mahomes"]  # Tier 1
        mult = calculate_strategy_multiplier(ps, draft_state)
        assert mult > 1.0

    def test_studs_and_steals_discounts_low_tiers(self, draft_state, _test_settings):
        _test_settings.draft_strategy = "studs_and_steals"
        # Need a tier 4+ player; modify one manually
        ps = draft_state.players["tyler bass"]
        ps.projection.tier = 4
        mult = calculate_strategy_multiplier(ps, draft_state)
        assert mult < 1.0

    def test_wr_heavy_boosts_wr(self, draft_state, _test_settings):
        _test_settings.draft_strategy = "wr_heavy"
        ps = draft_state.players["ceedee lamb"]
        mult = calculate_strategy_multiplier(ps, draft_state)
        assert mult > 1.0

    def test_elite_te_boosts_te(self, draft_state, _test_settings):
        _test_settings.draft_strategy = "elite_te"
        ps = draft_state.players["travis kelce"]
        mult = calculate_strategy_multiplier(ps, draft_state)
        assert mult > 1.0


# =====================================================================
# get_engine_advice (full advice generation)
# =====================================================================

class TestGetEngineAdvice:
    def test_buy_when_below_fmv(self, draft_state):
        """Should recommend BUY when current bid is below FMV."""
        advice = get_engine_advice("CeeDee Lamb", 10.0, draft_state)
        assert advice.action == AdviceAction.BUY
        assert advice.fmv > 0
        assert advice.max_bid > 0

    def test_pass_when_well_above_fmv(self, draft_state):
        """Should recommend PASS when current bid is well above FMV."""
        # CeeDee Lamb has FMV around $50 * inflation
        advice = get_engine_advice("CeeDee Lamb", 500.0, draft_state)
        assert advice.action == AdviceAction.PASS

    def test_unknown_player_pass(self, draft_state):
        """Unknown player should return PASS with 0 FMV."""
        advice = get_engine_advice("Totally Unknown Player", 10.0, draft_state)
        assert advice.action == AdviceAction.PASS
        assert advice.fmv == 0.0
        assert "not found" in advice.reasoning

    def test_no_current_bid_valuation(self, draft_state):
        """With current_bid <= 0, should provide valuation."""
        advice = get_engine_advice("Saquon Barkley", 0.0, draft_state)
        assert advice.action == AdviceAction.BUY  # Positive VORP player
        assert advice.fmv > 0
        assert "FMV" in advice.reasoning

    def test_no_slot_pass(self, draft_state):
        """When no roster slot is available, should PASS."""
        draft_state.my_team.roster["QB"] = "Some QB"
        advice = get_engine_advice("Josh Allen", 15.0, draft_state)
        # With QB slot full and no SUPERFLEX, should be PASS or PRICE_ENFORCE
        assert advice.action in (AdviceAction.PASS, AdviceAction.PRICE_ENFORCE)

    def test_price_enforce_cheap_no_slot(self, draft_state):
        """When player is going cheap but we don't need position, suggest PRICE_ENFORCE."""
        draft_state.my_team.roster["QB"] = "Some QB"
        # Set a low bid for a player with high FMV
        advice = get_engine_advice("Patrick Mahomes", 1.0, draft_state)
        assert advice.action == AdviceAction.PRICE_ENFORCE

    def test_advice_contains_vona(self, draft_state):
        advice = get_engine_advice("Saquon Barkley", 10.0, draft_state)
        assert advice.vona >= 0.0

    def test_advice_inflation_rate(self, draft_state):
        advice = get_engine_advice("CeeDee Lamb", 10.0, draft_state)
        assert advice.inflation_rate > 0

    def test_advice_scarcity_multiplier(self, draft_state):
        advice = get_engine_advice("CeeDee Lamb", 10.0, draft_state)
        assert advice.scarcity_multiplier >= 1.0

    def test_budget_cap(self, draft_state):
        """max_bid should never exceed budget max."""
        advice = get_engine_advice("Saquon Barkley", 10.0, draft_state)
        assert advice.max_bid <= draft_state.my_team.max_bid


# =====================================================================
# Edge Cases
# =====================================================================

class TestEdgeCases:
    def test_zero_budget(self, draft_state):
        draft_state.my_team.budget = 0
        advice = get_engine_advice("CeeDee Lamb", 1.0, draft_state)
        assert advice.max_bid <= 0

    def test_low_vorp_player(self, draft_state):
        """Players with low VORP should get PASS."""
        # Tyler Bass (K) likely has low VORP
        ps = draft_state.players["tyler bass"]
        ps.vorp = 0.0
        advice = get_engine_advice("Tyler Bass", 5.0, draft_state)
        assert advice.action == AdviceAction.PASS
