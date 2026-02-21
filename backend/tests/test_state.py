"""
Tests for state.py: DraftState CSV loading, draft event processing, queries, and aggregates.
"""

import pytest
from state import DraftState
from models import DraftUpdate, Position


class TestCSVLoading:
    def test_load_projections_populates_players(self, draft_state):
        assert len(draft_state.players) == 16

    def test_player_names_are_normalized_keys(self, draft_state):
        # "Patrick Mahomes" -> normalized key
        assert "patrick mahomes" in draft_state.players

    def test_player_projection_data(self, draft_state):
        ps = draft_state.players["patrick mahomes"]
        assert ps.projection.player_name == "Patrick Mahomes"
        assert ps.projection.position == Position.QB
        assert ps.projection.projected_points == 380.0
        assert ps.projection.baseline_aav == 25.0
        assert ps.projection.tier == 1

    def test_all_positions_loaded(self, draft_state):
        positions = {ps.projection.position.value for ps in draft_state.players.values()}
        assert positions == {"QB", "RB", "WR", "TE", "K", "DEF"}

    def test_vorp_computed_after_load(self, draft_state):
        # The best QB (Mahomes, 380pts) should have positive VORP
        ps = draft_state.players["patrick mahomes"]
        assert ps.vorp > 0

    def test_replacement_levels_computed(self, draft_state):
        assert "QB" in draft_state.replacement_level
        assert "RB" in draft_state.replacement_level
        assert "WR" in draft_state.replacement_level
        assert "TE" in draft_state.replacement_level

    def test_aggregates_computed(self, draft_state):
        assert draft_state.total_remaining_aav > 0
        assert draft_state.total_remaining_cash > 0
        assert draft_state.inflation_factor > 0

    def test_total_remaining_aav_is_sum(self, draft_state):
        expected_sum = sum(ps.projection.baseline_aav for ps in draft_state.players.values())
        assert abs(draft_state.total_remaining_aav - expected_sum) < 0.01

    def test_inflation_factor_with_no_budgets(self, draft_state):
        # No team budgets yet -> total_remaining_cash = league_size * budget = 10 * 200 = 2000
        expected = 2000.0 / draft_state.total_remaining_aav
        assert abs(draft_state.inflation_factor - expected) < 0.01

    def test_file_not_found_raises(self):
        state = DraftState()
        with pytest.raises(FileNotFoundError):
            state.load_projections("/nonexistent/path.csv")


class TestLoadFromMerged:
    def test_load_from_merged_rows(self, sample_csv_rows):
        state = DraftState()
        state.load_from_merged(sample_csv_rows)
        assert len(state.players) == 16
        assert "patrick mahomes" in state.players


class TestDraftEventProcessing:
    def test_update_marks_player_drafted(self, draft_state, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        ps = draft_state.players["patrick mahomes"]
        assert ps.is_drafted is True
        assert ps.draft_price == 30

    def test_update_tracks_team_name(self, draft_state, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        ps = draft_state.players["patrick mahomes"]
        assert ps.drafted_by_team == "Team Alpha"

    def test_update_team_budgets(self, draft_state, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        assert "Team Alpha" in draft_state.team_budgets
        assert draft_state.team_budgets["Team Alpha"] == 170

    def test_my_team_pick_updates_roster(self, draft_state):
        """When my team drafts a player, the roster is updated."""
        update_data = {
            "timestamp": 1700000001,
            "teams": [
                {"teamId": "2", "name": "My Team", "totalBudget": 200, "remainingBudget": 150, "rosterSize": 10},
            ],
            "draftLog": [
                {"playerId": "99", "playerName": "CeeDee Lamb", "teamId": "2", "bidAmount": 50},
            ],
            "rosters": {},
        }
        du = DraftUpdate(**update_data)
        draft_state.update_from_draft_event(du)

        # CeeDee Lamb should be in my team's roster
        assert "CeeDee Lamb" in draft_state.my_team.roster.values()
        assert draft_state.my_team.budget == 150

    def test_idempotent_updates(self, draft_state, sample_draft_update):
        """Processing the same update twice should not double-count."""
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)
        draft_state.update_from_draft_event(du)

        drafted_count = sum(1 for ps in draft_state.players.values() if ps.is_drafted)
        assert drafted_count == 1

    def test_newly_drafted_tracking(self, draft_state, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)
        assert len(draft_state.newly_drafted) == 1
        assert draft_state.newly_drafted[0].projection.player_name == "Patrick Mahomes"

    def test_second_update_detects_new(self, draft_state, sample_draft_update):
        """Second update with same log should have no newly_drafted."""
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        # Second update with the same log
        draft_state.update_from_draft_event(du)
        assert len(draft_state.newly_drafted) == 0

    def test_recompute_after_draft(self, draft_state, sample_draft_update):
        initial_aav = draft_state.total_remaining_aav
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        # AAV should decrease by Mahomes' baseline_aav (25.0)
        assert draft_state.total_remaining_aav < initial_aav

    def test_inflation_history_grows(self, draft_state, sample_draft_update):
        initial_len = len(draft_state.inflation_history)
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)
        assert len(draft_state.inflation_history) > initial_len


class TestGetPlayer:
    def test_exact_match(self, draft_state):
        ps = draft_state.get_player("Patrick Mahomes")
        assert ps is not None
        assert ps.projection.player_name == "Patrick Mahomes"

    def test_case_insensitive(self, draft_state):
        ps = draft_state.get_player("patrick mahomes")
        assert ps is not None

    def test_fuzzy_match_suffix(self, draft_state):
        """Fuzzy matching should handle suffix variations."""
        # "Derrick Henry" is in our data; "Derrick Henry Jr." should fuzzy match
        ps = draft_state.get_player("Derrick Henry Jr.")
        assert ps is not None
        assert ps.projection.player_name == "Derrick Henry"

    def test_missing_player(self, draft_state):
        ps = draft_state.get_player("Nonexistent Player XYZ")
        assert ps is None


class TestGetRemainingPlayers:
    def test_all_remaining_initially(self, draft_state):
        remaining = draft_state.get_remaining_players()
        assert len(remaining) == 16

    def test_filter_by_position(self, draft_state):
        qbs = draft_state.get_remaining_players("QB")
        assert all(ps.projection.position == Position.QB for ps in qbs)
        assert len(qbs) == 4  # We have 4 QBs

    def test_sorted_by_vorp_desc(self, draft_state):
        remaining = draft_state.get_remaining_players()
        for i in range(len(remaining) - 1):
            assert remaining[i].vorp >= remaining[i + 1].vorp

    def test_drafted_excluded(self, draft_state, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        remaining = draft_state.get_remaining_players("QB")
        names = [ps.projection.player_name for ps in remaining]
        assert "Patrick Mahomes" not in names

    def test_remaining_count_decreases(self, draft_state, sample_draft_update):
        before = len(draft_state.get_remaining_players())
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)
        after = len(draft_state.get_remaining_players())
        assert after == before - 1


class TestStarterNeed:
    def test_initial_starter_needs(self, draft_state):
        needs = draft_state.get_starter_need()
        # All positions should have open starter slots
        assert needs["QB"] >= 1
        assert needs["RB"] >= 2
        assert needs["WR"] >= 2

    def test_starter_need_decreases(self, draft_state):
        """After drafting a WR for my team, WR starter need decreases."""
        update_data = {
            "teams": [
                {"teamId": "2", "name": "My Team", "remainingBudget": 150, "rosterSize": 10},
            ],
            "draftLog": [
                {"playerName": "CeeDee Lamb", "teamId": "2", "bidAmount": 50},
            ],
            "rosters": {},
        }
        du = DraftUpdate(**update_data)

        needs_before = draft_state.get_starter_need()
        draft_state.update_from_draft_event(du)
        needs_after = draft_state.get_starter_need()

        # WR need should decrease (could go into WR or FLEX slot)
        assert needs_after["WR"] < needs_before["WR"]


class TestRecomputeAggregates:
    def test_inflation_changes_with_budgets(self, draft_state):
        # Manually set team budgets lower than default
        draft_state.team_budgets = {"Team A": 100, "Team B": 100}
        draft_state._recompute_aggregates()

        # Total cash is now 200 instead of 2000
        assert draft_state.total_remaining_cash == 200

    def test_inflation_factor_when_aav_is_zero(self, draft_state):
        # Mark all players as drafted to zero out AAV
        for ps in draft_state.players.values():
            ps.is_drafted = True
        draft_state._recompute_aggregates()

        # Should default to 1.0 when no AAV remains
        assert draft_state.inflation_factor == 1.0


class TestReset:
    def test_reset_clears_draft_progress(self, draft_state, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        # Verify player is drafted
        assert draft_state.players["patrick mahomes"].is_drafted is True

        draft_state.reset()

        # After reset, player should be undrafted
        assert draft_state.players["patrick mahomes"].is_drafted is False
        assert draft_state.players["patrick mahomes"].draft_price is None

    def test_reset_clears_budgets(self, draft_state, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)
        draft_state.reset()

        assert len(draft_state.team_budgets) == 0
        assert draft_state.my_team.budget == draft_state.my_team.total_budget

    def test_reset_clears_roster(self, draft_state):
        draft_state.my_team.roster["QB"] = "Patrick Mahomes"
        draft_state.reset()
        assert all(v is None for v in draft_state.my_team.roster.values())


class TestRosterSlotAssignment:
    def test_dedicated_slot_first(self, draft_state):
        """Player should go to dedicated position slot before flex."""
        update_data = {
            "teams": [
                {"teamId": "2", "name": "My Team", "remainingBudget": 150, "rosterSize": 10},
            ],
            "draftLog": [
                {"playerName": "Saquon Barkley", "teamId": "2", "bidAmount": 55},
            ],
            "rosters": {},
        }
        du = DraftUpdate(**update_data)
        draft_state.update_from_draft_event(du)

        # Should go to RB1 (or RB2), not FLEX
        rb_slots = [s for s, v in draft_state.my_team.roster.items()
                     if v == "Saquon Barkley"]
        assert len(rb_slots) == 1
        slot = rb_slots[0]
        base = draft_state.my_team.slot_types.get(slot, slot.rstrip("0123456789"))
        assert base == "RB"

    def test_flex_slot_after_dedicated_full(self, draft_state):
        """After filling both RB slots, next RB goes to FLEX."""
        # Fill RB1 and RB2
        for name in ["Saquon Barkley", "Breece Hall"]:
            update_data = {
                "teams": [
                    {"teamId": "2", "name": "My Team", "remainingBudget": 100, "rosterSize": 10},
                ],
                "draftLog": [
                    {"playerName": name, "teamId": "2", "bidAmount": 50},
                ],
                "rosters": {},
            }
            du = DraftUpdate(**update_data)
            draft_state.update_from_draft_event(du)

        # Now add a third RB
        update_data = {
            "teams": [
                {"teamId": "2", "name": "My Team", "remainingBudget": 60, "rosterSize": 10},
            ],
            "draftLog": [
                {"playerName": "Bijan Robinson", "teamId": "2", "bidAmount": 40},
            ],
            "rosters": {},
        }
        du = DraftUpdate(**update_data)
        draft_state.update_from_draft_event(du)

        # Third RB should be in FLEX slot
        flex_slots = [s for s, v in draft_state.my_team.roster.items()
                      if v == "Bijan Robinson"]
        assert len(flex_slots) == 1
        slot = flex_slots[0]
        base = draft_state.my_team.slot_types.get(slot, slot.rstrip("0123456789"))
        assert base == "FLEX"


class TestStateSummary:
    def test_get_state_summary_structure(self, draft_state):
        summary = draft_state.get_state_summary()
        assert "total_players" in summary
        assert "drafted" in summary
        assert "remaining" in summary
        assert "inflation_factor" in summary
        assert "my_team" in summary
        assert "positional_need" in summary

    def test_summary_counts_correct(self, draft_state, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        summary = draft_state.get_state_summary()
        assert summary["total_players"] == 16
        assert summary["drafted"] == 1
        assert summary["remaining"] == 15
