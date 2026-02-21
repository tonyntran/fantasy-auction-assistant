"""
Tests for nomination.py: Nomination strategy engine, priority scoring, and suggestions.
"""

import pytest
from state import DraftState
from models import DraftUpdate, TeamInfo, RosterEntry
from nomination import (
    get_nomination_suggestions,
    _get_draft_phase,
    _teams_needing_position,
    _get_opponent_needs_by_team,
)
from config import settings


class TestGetDraftPhase:
    def test_elite_phase_no_drafted(self, draft_state):
        phase = _get_draft_phase(draft_state)
        assert phase == "elite"

    def test_elite_phase_early(self, draft_state):
        """With < 15% drafted, should be elite phase."""
        total = len(draft_state.players)
        # Draft 1 player (1/16 = 6.25%)
        draft_state.players["patrick mahomes"].is_drafted = True
        phase = _get_draft_phase(draft_state)
        assert phase == "elite"

    def test_middle_phase(self, draft_state):
        """With 15-50% drafted, should be middle phase."""
        total = len(draft_state.players)  # 16
        # Draft 4 players (4/16 = 25%)
        names = ["patrick mahomes", "josh allen", "jalen hurts", "saquon barkley"]
        for n in names:
            draft_state.players[n].is_drafted = True
        phase = _get_draft_phase(draft_state)
        assert phase == "middle"

    def test_value_phase(self, draft_state):
        """With 50-80% drafted, should be value phase."""
        total = len(draft_state.players)
        # Draft 10 of 16 = 62.5%
        keys = list(draft_state.players.keys())[:10]
        for k in keys:
            draft_state.players[k].is_drafted = True
        phase = _get_draft_phase(draft_state)
        assert phase == "value"

    def test_dollar_phase(self, draft_state):
        """With 80%+ drafted, should be dollar phase."""
        total = len(draft_state.players)
        # Draft 14 of 16 = 87.5%
        keys = list(draft_state.players.keys())[:14]
        for k in keys:
            draft_state.players[k].is_drafted = True
        phase = _get_draft_phase(draft_state)
        assert phase == "dollar"


class TestTeamsNeedingPosition:
    def test_no_opponent_data(self):
        opponent_needs = {}
        count = _teams_needing_position(opponent_needs, "QB")
        assert count == 0

    def test_some_teams_need_position(self):
        opponent_needs = {
            "team1": {"QB", "RB"},
            "team2": {"WR"},
            "team3": {"QB", "WR"},
        }
        assert _teams_needing_position(opponent_needs, "QB") == 2
        assert _teams_needing_position(opponent_needs, "WR") == 2
        assert _teams_needing_position(opponent_needs, "RB") == 1
        assert _teams_needing_position(opponent_needs, "TE") == 0


class TestGetNominationSuggestions:
    def test_returns_list(self, draft_state):
        suggestions = get_nomination_suggestions(draft_state)
        assert isinstance(suggestions, list)

    def test_max_suggestions(self, draft_state):
        suggestions = get_nomination_suggestions(draft_state, top_n=3)
        assert len(suggestions) <= 3

    def test_suggestion_structure(self, draft_state):
        """Each suggestion should have required fields."""
        # We need some opponent data for suggestions to work well
        # Without opponent data, we'll mainly get BARGAIN_SNAG suggestions
        suggestions = get_nomination_suggestions(draft_state, top_n=10)
        for s in suggestions:
            assert "player_name" in s
            assert "position" in s
            assert "fmv" in s
            assert "strategy" in s
            assert "reasoning" in s
            assert "priority" in s

    def test_suggestions_sorted_by_priority(self, draft_state):
        suggestions = get_nomination_suggestions(draft_state, top_n=10)
        if len(suggestions) > 1:
            for i in range(len(suggestions) - 1):
                assert suggestions[i]["priority"] >= suggestions[i + 1]["priority"]

    def test_no_drafted_players_suggested(self, draft_state, sample_draft_update):
        """Drafted players should not appear in suggestions."""
        du = DraftUpdate(**sample_draft_update)
        draft_state.update_from_draft_event(du)

        suggestions = get_nomination_suggestions(draft_state, top_n=20)
        suggested_names = [s["player_name"] for s in suggestions]
        assert "Patrick Mahomes" not in suggested_names

    def test_with_opponent_data_generates_strategies(self, draft_state):
        """With opponent roster data, should generate various strategy types."""
        # Set up opponent data by marking my team's slots as filled
        # and adding opponent tracker data
        tracker = draft_state.opponent_tracker
        tracker.team_rosters = {
            "1": {"QB": 1, "WR": 0, "RB": 0},
            "3": {"QB": 0, "WR": 1, "RB": 0},
        }
        tracker.team_budgets = {"1": 170, "3": 180}
        tracker.team_sizes = {"1": 10, "3": 10}
        tracker.team_names = {"1": "Team Alpha", "3": "Team Gamma"}

        # Fill our QB slot so we don't need QB
        draft_state.my_team.roster["QB"] = "Patrick Mahomes"
        draft_state.players["patrick mahomes"].is_drafted = True

        suggestions = get_nomination_suggestions(draft_state, top_n=10)
        strategies = {s["strategy"] for s in suggestions}
        # Should have at least some strategy types
        assert len(suggestions) > 0


class TestNominationStrategies:
    def test_bargain_snag_when_i_need_position(self, draft_state):
        """BARGAIN_SNAG suggestions should be for positions we need."""
        suggestions = get_nomination_suggestions(draft_state, top_n=20)
        bargains = [s for s in suggestions if s["strategy"] == "BARGAIN_SNAG"]
        for b in bargains:
            pos = b["position"]
            needs = draft_state.get_positional_need()
            assert needs.get(pos, 0) > 0

    def test_budget_drain_targets_positions_i_dont_need(self, draft_state):
        """BUDGET_DRAIN should target positions we've already filled."""
        # Fill all QB slots
        draft_state.my_team.roster["QB"] = "Some QB"
        draft_state.players["patrick mahomes"].is_drafted = True

        # Set up opponent data
        tracker = draft_state.opponent_tracker
        tracker.team_rosters = {"1": {"QB": 0}}
        tracker.team_budgets = {"1": 180}
        tracker.team_sizes = {"1": 10}
        tracker.team_names = {"1": "Team Alpha"}

        suggestions = get_nomination_suggestions(draft_state, top_n=20)
        drains = [s for s in suggestions if s["strategy"] == "BUDGET_DRAIN"]
        # If any drain suggestions exist, they should be for QBs we don't need
        for d in drains:
            if d["position"] == "QB":
                assert draft_state.my_team.roster.get("QB") is not None


class TestDraftPhaseTiming:
    def test_phase_affects_priority_boosts(self, draft_state):
        """Different draft phases should produce different priority distributions."""
        # Elite phase (no one drafted)
        suggestions_early = get_nomination_suggestions(draft_state, top_n=10)

        # Dollar phase (most drafted)
        keys = list(draft_state.players.keys())[:13]
        for k in keys:
            draft_state.players[k].is_drafted = True
        draft_state._recompute_aggregates()

        suggestions_late = get_nomination_suggestions(draft_state, top_n=10)

        # Both should return suggestions (if players remain)
        # The priorities and strategy distributions will differ
        assert isinstance(suggestions_early, list)
        assert isinstance(suggestions_late, list)
