"""
Tests for Pydantic models: DraftUpdate, PlayerProjection, MyTeamState, Position enum.
"""

import pytest
from models import (
    DraftUpdate,
    NominationInfo,
    TeamInfo,
    DraftLogEntry,
    RosterEntry,
    PlayerProjection,
    PlayerState,
    MyTeamState,
    Position,
    AdviceAction,
    EngineAdvice,
)


# =====================================================================
# Position Enum
# =====================================================================

class TestPosition:
    def test_football_positions(self):
        assert Position.QB == "QB"
        assert Position.RB == "RB"
        assert Position.WR == "WR"
        assert Position.TE == "TE"
        assert Position.K == "K"
        assert Position.DEF == "DEF"

    def test_basketball_positions(self):
        assert Position.PG == "PG"
        assert Position.SG == "SG"
        assert Position.SF == "SF"
        assert Position.PF == "PF"
        assert Position.C == "C"

    def test_position_is_string_enum(self):
        assert isinstance(Position.QB, str)
        assert Position.QB.value == "QB"

    def test_invalid_position_raises(self):
        with pytest.raises(ValueError):
            Position("INVALID")


# =====================================================================
# PlayerProjection
# =====================================================================

class TestPlayerProjection:
    def test_valid_creation(self):
        p = PlayerProjection(
            player_name="Patrick Mahomes",
            position=Position.QB,
            projected_points=380.0,
            baseline_aav=25.0,
            tier=1,
        )
        assert p.player_name == "Patrick Mahomes"
        assert p.position == Position.QB
        assert p.projected_points == 380.0
        assert p.baseline_aav == 25.0
        assert p.tier == 1

    def test_position_from_string(self):
        p = PlayerProjection(
            player_name="Test",
            position="RB",
            projected_points=100.0,
            baseline_aav=10.0,
            tier=2,
        )
        assert p.position == Position.RB

    def test_missing_required_field_raises(self):
        with pytest.raises(Exception):
            PlayerProjection(
                player_name="Test",
                # position missing
                projected_points=100.0,
                baseline_aav=10.0,
                tier=1,
            )


# =====================================================================
# PlayerState
# =====================================================================

class TestPlayerState:
    def test_defaults(self):
        proj = PlayerProjection(
            player_name="Test",
            position=Position.WR,
            projected_points=200.0,
            baseline_aav=20.0,
            tier=2,
        )
        ps = PlayerState(projection=proj)
        assert ps.is_drafted is False
        assert ps.draft_price is None
        assert ps.drafted_by_team is None
        assert ps.vorp == 0.0
        assert ps.vona == 0.0
        assert ps.vona_next_player is None
        assert ps.adp_value is None

    def test_drafted_state(self):
        proj = PlayerProjection(
            player_name="Test",
            position=Position.QB,
            projected_points=300.0,
            baseline_aav=20.0,
            tier=1,
        )
        ps = PlayerState(projection=proj, is_drafted=True, draft_price=25, drafted_by_team="Team A")
        assert ps.is_drafted is True
        assert ps.draft_price == 25
        assert ps.drafted_by_team == "Team A"


# =====================================================================
# DraftUpdate Validation
# =====================================================================

class TestDraftUpdate:
    def test_valid_payload(self, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        assert du.timestamp == 1700000000
        assert du.currentNomination.playerName == "Patrick Mahomes"
        assert du.currentBid == 30.0
        assert du.highBidder == "Team Alpha"
        assert len(du.teams) == 3
        assert len(du.draftLog) == 1
        assert du.source == "test"
        assert du.sport == "football"
        assert du.platform == "sleeper"

    def test_minimal_payload(self):
        du = DraftUpdate()
        assert du.timestamp is None
        assert du.currentNomination is None
        assert du.currentBid is None
        assert du.teams == []
        assert du.draftLog == []
        assert du.rosters == {}
        assert du.source is None

    def test_extra_fields_allowed(self):
        du = DraftUpdate(unknownField="extra_data")
        assert du.unknownField == "extra_data"

    def test_teams_parse_correctly(self, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        team_alpha = du.teams[0]
        assert team_alpha.name == "Team Alpha"
        assert team_alpha.remainingBudget == 170
        assert team_alpha.totalBudget == 200

    def test_draft_log_entry_parsing(self, sample_draft_update):
        du = DraftUpdate(**sample_draft_update)
        entry = du.draftLog[0]
        assert entry.playerName == "Patrick Mahomes"
        assert entry.bidAmount == 30
        assert entry.keeper is False

    def test_nomination_info(self):
        ni = NominationInfo(playerId=123, playerName="Josh Allen", nominatingTeamId=5)
        assert ni.playerId == 123
        assert ni.playerName == "Josh Allen"

    def test_nomination_info_defaults(self):
        ni = NominationInfo()
        assert ni.playerId is None
        assert ni.playerName == "Unknown"

    def test_draft_log_entry_defaults(self):
        entry = DraftLogEntry()
        assert entry.playerName == "Unknown"
        assert entry.bidAmount == 0
        assert entry.keeper is False

    def test_team_info_defaults(self):
        ti = TeamInfo()
        assert ti.name == "Unknown"
        assert ti.totalBudget == 200
        assert ti.remainingBudget is None


# =====================================================================
# MyTeamState
# =====================================================================

class TestMyTeamState:
    @pytest.fixture
    def team(self):
        return MyTeamState(
            team_name="My Team",
            budget=200,
            total_budget=200,
            roster={
                "QB": None,
                "RB1": None,
                "RB2": None,
                "WR1": None,
                "WR2": None,
                "TE": None,
                "FLEX1": None,
                "FLEX2": None,
                "K": None,
                "DEF": None,
            },
            slot_types={
                "QB": "QB",
                "RB1": "RB",
                "RB2": "RB",
                "WR1": "WR",
                "WR2": "WR",
                "TE": "TE",
                "FLEX1": "FLEX",
                "FLEX2": "FLEX",
                "K": "K",
                "DEF": "DEF",
            },
        )

    @pytest.fixture
    def slot_eligibility(self):
        return {
            "QB": ["QB"],
            "RB": ["RB"],
            "WR": ["WR"],
            "TE": ["TE"],
            "K": ["K"],
            "DEF": ["DEF"],
            "FLEX": ["RB", "WR", "TE"],
            "BENCH": ["QB", "RB", "WR", "TE", "K", "DEF"],
        }

    def test_roster_spots_remaining_all_empty(self, team):
        assert team.roster_spots_remaining == 10

    def test_roster_spots_remaining_some_filled(self, team):
        team.roster["QB"] = "Patrick Mahomes"
        team.roster["RB1"] = "Saquon Barkley"
        assert team.roster_spots_remaining == 8

    def test_max_bid_all_empty(self, team):
        # 200 budget, 10 empty -> max_bid = 200 - 9 = 191
        assert team.max_bid == 191

    def test_max_bid_one_spot_left(self, team):
        for slot in list(team.roster.keys())[:-1]:
            team.roster[slot] = "Player"
        # 1 empty slot, budget 200 -> max_bid = 200
        assert team.max_bid == 200

    def test_max_bid_no_spots(self, team):
        for slot in team.roster:
            team.roster[slot] = "Player"
        # 0 empty -> max_bid = budget (no reservation needed)
        assert team.max_bid == 200

    def test_open_slots_for_position_rb(self, team, slot_eligibility):
        """RB should have RB1, RB2, FLEX1, FLEX2 open."""
        open_slots = team.open_slots_for_position("RB", slot_eligibility)
        assert "RB1" in open_slots
        assert "RB2" in open_slots
        assert "FLEX1" in open_slots
        assert "FLEX2" in open_slots

    def test_open_slots_for_position_qb(self, team, slot_eligibility):
        """QB should only have QB slot open (not flex-eligible by default)."""
        open_slots = team.open_slots_for_position("QB", slot_eligibility)
        assert open_slots == ["QB"]

    def test_open_slots_after_filling(self, team, slot_eligibility):
        """After filling RB1, RB should still have RB2, FLEX1, FLEX2."""
        team.roster["RB1"] = "Saquon Barkley"
        open_slots = team.open_slots_for_position("RB", slot_eligibility)
        assert "RB1" not in open_slots
        assert "RB2" in open_slots

    def test_can_still_start(self, team, slot_eligibility):
        assert team.can_still_start("RB", slot_eligibility) is True

    def test_cannot_start_when_full(self, team, slot_eligibility):
        """After filling QB slot, QB can't start."""
        team.roster["QB"] = "Patrick Mahomes"
        assert team.can_still_start("QB", slot_eligibility) is False

    def test_positional_need_summary(self, team, slot_eligibility):
        needs = team.positional_need_summary(slot_eligibility)
        # QB has 1 slot, RB has 2+2 flex = 4, WR has 2+2 flex = 4, TE has 1+2 flex = 3
        assert needs["QB"] == 1
        assert needs["RB"] == 4  # RB1, RB2, FLEX1, FLEX2
        assert needs["WR"] == 4  # WR1, WR2, FLEX1, FLEX2
        assert needs["TE"] == 3  # TE, FLEX1, FLEX2
        assert needs["K"] == 1
        assert needs["DEF"] == 1

    def test_positional_need_summary_exclude_bench(self, team, slot_eligibility):
        """When we add bench slots, exclude_bench should not count them."""
        team.roster["BENCH1"] = None
        team.slot_types["BENCH1"] = "BENCH"
        needs = team.positional_need_summary(slot_eligibility, exclude_bench=True)
        # Bench slot should not be counted
        assert needs["QB"] == 1

    def test_bench_spots_remaining(self, team):
        # No bench slots in this fixture
        assert team.bench_spots_remaining == 0

    def test_bench_spots_remaining_with_bench(self, team):
        team.roster["BENCH1"] = None
        team.roster["BENCH2"] = None
        team.slot_types["BENCH1"] = "BENCH"
        team.slot_types["BENCH2"] = "BENCH"
        assert team.bench_spots_remaining == 2

    def test_bench_spots_decreases_when_filled(self, team):
        team.roster["BENCH1"] = None
        team.roster["BENCH2"] = None
        team.slot_types["BENCH1"] = "BENCH"
        team.slot_types["BENCH2"] = "BENCH"
        team.roster["BENCH1"] = "Some Player"
        assert team.bench_spots_remaining == 1


# =====================================================================
# AdviceAction Enum
# =====================================================================

class TestAdviceAction:
    def test_values(self):
        assert AdviceAction.BUY == "BUY"
        assert AdviceAction.PASS == "PASS"
        assert AdviceAction.PRICE_ENFORCE == "PRICE_ENFORCE"
        assert AdviceAction.NOMINATE == "NOMINATE"
