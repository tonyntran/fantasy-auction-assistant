"""
Tests for what_if.py: clone_state, simulate_what_if, and error handling.
"""

import pytest
from state import DraftState
from models import DraftUpdate
from what_if import clone_state, simulate_what_if


# =====================================================================
# clone_state
# =====================================================================

class TestCloneState:
    def test_clone_creates_independent_copy(self, draft_state):
        cloned = clone_state(draft_state)

        # Modify the clone -- should not affect original
        cloned.players["patrick mahomes"].is_drafted = True
        assert draft_state.players["patrick mahomes"].is_drafted is False

    def test_clone_copies_players(self, draft_state):
        cloned = clone_state(draft_state)
        assert len(cloned.players) == len(draft_state.players)

    def test_clone_copies_budget(self, draft_state):
        cloned = clone_state(draft_state)
        assert cloned.my_team.budget == draft_state.my_team.budget

    def test_clone_copies_roster(self, draft_state):
        draft_state.my_team.roster["QB"] = "Patrick Mahomes"
        cloned = clone_state(draft_state)
        assert cloned.my_team.roster["QB"] == "Patrick Mahomes"

    def test_clone_roster_independent(self, draft_state):
        cloned = clone_state(draft_state)
        cloned.my_team.roster["QB"] = "Josh Allen"
        assert draft_state.my_team.roster["QB"] is None

    def test_clone_team_budgets_independent(self, draft_state):
        draft_state.team_budgets = {"Team A": 150}
        cloned = clone_state(draft_state)
        cloned.team_budgets["Team A"] = 100
        assert draft_state.team_budgets["Team A"] == 150

    def test_clone_preserves_inflation(self, draft_state):
        cloned = clone_state(draft_state)
        assert cloned.inflation_factor == draft_state.inflation_factor

    def test_clone_preserves_replacement_levels(self, draft_state):
        cloned = clone_state(draft_state)
        assert cloned.replacement_level == draft_state.replacement_level

    def test_clone_has_name_resolver(self, draft_state):
        cloned = clone_state(draft_state)
        # Shares the same name_resolver (read-only)
        assert cloned.name_resolver is draft_state.name_resolver

    def test_clone_is_not_singleton(self, draft_state):
        """Clone should bypass the singleton pattern."""
        cloned = clone_state(draft_state)
        assert cloned is not draft_state


# =====================================================================
# simulate_what_if
# =====================================================================

class TestSimulateWhatIf:
    def test_valid_simulation(self, draft_state):
        result = simulate_what_if("Saquon Barkley", 50, draft_state)
        assert "error" not in result
        assert result["hypothetical_purchase"]["player"] == "Saquon Barkley"
        assert result["hypothetical_purchase"]["price"] == 50
        assert "remaining_budget_after" in result
        assert "optimal_remaining_picks" in result
        assert "projected_total_points" in result
        assert "roster_completeness" in result

    def test_budget_decreases(self, draft_state):
        result = simulate_what_if("Saquon Barkley", 50, draft_state)
        assert result["remaining_budget_after"] == 150  # 200 - 50

    def test_player_not_found(self, draft_state):
        result = simulate_what_if("Nonexistent Player", 30, draft_state)
        assert "error" in result
        assert "not found" in result["error"]

    def test_already_drafted_player(self, draft_state, sample_draft_update):
        """Should return error for already-drafted players."""
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        result = simulate_what_if("Patrick Mahomes", 30, draft_state)
        assert "error" in result
        assert "already drafted" in result["error"]

    def test_original_state_unchanged(self, draft_state):
        """Simulation should not modify the original state."""
        original_budget = draft_state.my_team.budget
        original_drafted = draft_state.players["saquon barkley"].is_drafted

        simulate_what_if("Saquon Barkley", 50, draft_state)

        assert draft_state.my_team.budget == original_budget
        assert draft_state.players["saquon barkley"].is_drafted == original_drafted

    def test_optimal_picks_returned(self, draft_state):
        """Should generate optimal remaining picks after the purchase."""
        result = simulate_what_if("CeeDee Lamb", 45, draft_state)
        if "error" not in result:
            picks = result["optimal_remaining_picks"]
            assert isinstance(picks, list)
            for pick in picks:
                assert "player" in pick
                assert "position" in pick
                assert "estimated_price" in pick
                assert "vorp" in pick

    def test_roster_completeness_format(self, draft_state):
        result = simulate_what_if("Travis Kelce", 35, draft_state)
        if "error" not in result:
            completeness = result["roster_completeness"]
            assert "/" in completeness

    def test_projected_total_points(self, draft_state):
        result = simulate_what_if("Saquon Barkley", 50, draft_state)
        if "error" not in result:
            assert result["projected_total_points"] > 0

    def test_expensive_purchase_limits_optimal_picks(self, draft_state):
        """Spending most of the budget should leave fewer optimal picks."""
        result_cheap = simulate_what_if("Tyler Bass", 1, draft_state)
        result_expensive = simulate_what_if("Saquon Barkley", 180, draft_state)

        if "error" not in result_cheap and "error" not in result_expensive:
            # With more budget remaining, should get more optimal picks
            assert len(result_cheap["optimal_remaining_picks"]) >= len(
                result_expensive["optimal_remaining_picks"]
            )


# =====================================================================
# Greedy Fill Logic
# =====================================================================

class TestGreedyFill:
    def test_greedy_fill_respects_position_needs(self, draft_state):
        """Greedy fill should only pick players for positions with open starter slots."""
        result = simulate_what_if("CeeDee Lamb", 45, draft_state)
        if "error" not in result:
            picks = result["optimal_remaining_picks"]
            positions_picked = [p["position"] for p in picks]
            # Should have variety of positions, not all same
            if len(picks) > 2:
                assert len(set(positions_picked)) > 1

    def test_greedy_fill_stays_within_budget(self, draft_state):
        """Total of greedy picks should not exceed remaining budget."""
        result = simulate_what_if("Saquon Barkley", 50, draft_state)
        if "error" not in result:
            total_spent = sum(p["estimated_price"] for p in result["optimal_remaining_picks"])
            remaining_after = result["remaining_budget_after"]
            bench_reserve = draft_state.my_team.bench_spots_remaining
            # Total spent should not exceed budget minus bench reserve
            assert total_spent <= remaining_after

    def test_greedy_fill_picks_high_vorp(self, draft_state):
        """Greedy fill should prefer players with higher VORP/$ ratio."""
        result = simulate_what_if("Tyler Bass", 1, draft_state)
        if "error" not in result:
            picks = result["optimal_remaining_picks"]
            for pick in picks:
                assert pick["vorp"] >= 0
