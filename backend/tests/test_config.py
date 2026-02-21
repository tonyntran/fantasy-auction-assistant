"""
Tests for config.py: Settings defaults, roster parsing, sport profiles, slot mapping.
"""

import pytest
from config import Settings, SPORT_PROFILES, DRAFT_STRATEGIES


class TestSettingsDefaults:
    def test_default_platform(self):
        s = Settings(
            _env_file=None,
            platform="sleeper",
        )
        assert s.platform == "sleeper"

    def test_default_ai_provider(self):
        s = Settings(_env_file=None)
        assert s.ai_provider == "claude"

    def test_default_league_size(self):
        s = Settings(_env_file=None)
        assert s.league_size == 10

    def test_default_budget(self):
        s = Settings(_env_file=None)
        assert s.budget == 200

    def test_default_sport(self):
        s = Settings(_env_file=None)
        assert s.sport == "football"


class TestRosterSlotsParsing:
    def test_default_football_roster(self):
        s = Settings(_env_file=None)
        slots = s.parsed_roster_slots
        # Default: QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF
        assert "QB" in slots
        assert "RB1" in slots
        assert "RB2" in slots
        assert "WR1" in slots
        assert "WR2" in slots
        assert "TE" in slots
        assert "FLEX1" in slots
        assert "FLEX2" in slots
        assert "K" in slots
        assert "DEF" in slots
        assert len(slots) == 10

    def test_single_slots_no_numbering(self):
        s = Settings(_env_file=None, roster_slots="QB,RB,WR,TE,K,DEF")
        slots = s.parsed_roster_slots
        # All unique -- no numbering
        assert slots == ["QB", "RB", "WR", "TE", "K", "DEF"]

    def test_duplicate_slots_get_numbered(self):
        s = Settings(_env_file=None, roster_slots="RB,RB,RB")
        slots = s.parsed_roster_slots
        assert slots == ["RB1", "RB2", "RB3"]

    def test_roster_size(self):
        s = Settings(_env_file=None, roster_slots="QB,RB,WR")
        assert s.roster_size == 3

    def test_roster_size_default(self):
        s = Settings(_env_file=None)
        assert s.roster_size == 10


class TestSlotBaseType:
    def test_slot_base_type_mapping(self):
        s = Settings(_env_file=None)
        sbt = s.slot_base_type
        assert sbt["QB"] == "QB"
        assert sbt["RB1"] == "RB"
        assert sbt["RB2"] == "RB"
        assert sbt["FLEX1"] == "FLEX"
        assert sbt["FLEX2"] == "FLEX"
        assert sbt["K"] == "K"
        assert sbt["DEF"] == "DEF"

    def test_slot_base_type_custom_roster(self):
        s = Settings(_env_file=None, roster_slots="QB,QB,SUPERFLEX")
        sbt = s.slot_base_type
        assert sbt["QB1"] == "QB"
        assert sbt["QB2"] == "QB"
        assert sbt["SUPERFLEX"] == "SUPERFLEX"


class TestSportProfiles:
    def test_football_profile_exists(self):
        assert "football" in SPORT_PROFILES

    def test_basketball_profile_exists(self):
        assert "basketball" in SPORT_PROFILES

    def test_football_positions(self):
        fp = SPORT_PROFILES["football"]
        assert fp["positions"] == ["QB", "RB", "WR", "TE", "K", "DEF"]

    def test_basketball_positions(self):
        bp = SPORT_PROFILES["basketball"]
        assert bp["positions"] == ["PG", "SG", "SF", "PF", "C"]

    def test_football_season_games(self):
        assert SPORT_PROFILES["football"]["season_games"] == 17

    def test_basketball_season_games(self):
        assert SPORT_PROFILES["basketball"]["season_games"] == 82

    def test_football_slot_eligibility_flex(self):
        elig = SPORT_PROFILES["football"]["slot_eligibility"]
        assert "RB" in elig["FLEX"]
        assert "WR" in elig["FLEX"]
        assert "TE" in elig["FLEX"]
        assert "QB" not in elig["FLEX"]

    def test_basketball_util_eligibility(self):
        elig = SPORT_PROFILES["basketball"]["slot_eligibility"]
        assert set(elig["UTIL"]) == {"PG", "SG", "SF", "PF", "C"}

    def test_sport_profile_resolution_football(self):
        s = Settings(_env_file=None, sport="football")
        assert s.sport_profile["sport_name"] == "football"
        assert s.display_positions == ["QB", "RB", "WR", "TE"]

    def test_sport_profile_resolution_basketball(self):
        s = Settings(_env_file=None, sport="basketball")
        assert s.sport_profile["sport_name"] == "basketball"
        assert s.display_positions == ["PG", "SG", "SF", "PF", "C"]

    def test_auto_sport_falls_back_to_football(self):
        s = Settings(_env_file=None, sport="auto")
        assert s.sport_profile["sport_name"] == "football"

    def test_basketball_overrides_roster_slots(self):
        s = Settings(_env_file=None, sport="basketball")
        assert s.roster_slots == "PG,SG,G,SF,PF,F,C,UTIL,UTIL,UTIL"

    def test_basketball_overrides_slot_eligibility(self):
        s = Settings(_env_file=None, sport="basketball")
        assert "UTIL" in s.SLOT_ELIGIBILITY


class TestDraftStrategies:
    def test_balanced_strategy_exists(self):
        assert "balanced" in DRAFT_STRATEGIES

    def test_balanced_no_weights(self):
        balanced = DRAFT_STRATEGIES["balanced"]
        assert balanced["position_weights"] == {}
        assert balanced["tier_weights"] == {}

    def test_studs_and_steals_tier_weights(self):
        ss = DRAFT_STRATEGIES["studs_and_steals"]
        assert ss["tier_weights"][1] == 1.15
        assert ss["tier_weights"][5] == 0.80

    def test_rb_heavy_position_weights(self):
        rb = DRAFT_STRATEGIES["rb_heavy"]
        assert rb["position_weights"]["RB"] == 1.3
        assert rb["position_weights"]["QB"] == 0.9

    def test_active_strategy_default(self):
        s = Settings(_env_file=None)
        assert s.active_strategy == DRAFT_STRATEGIES["balanced"]

    def test_active_strategy_custom(self):
        s = Settings(_env_file=None, draft_strategy="rb_heavy")
        assert s.active_strategy == DRAFT_STRATEGIES["rb_heavy"]

    def test_active_strategy_invalid_falls_back(self):
        s = Settings(_env_file=None, draft_strategy="nonexistent")
        assert s.active_strategy == DRAFT_STRATEGIES["balanced"]


class TestVorpBaselines:
    def test_football_baselines(self):
        s = Settings(_env_file=None, sport="football")
        baselines = s.vorp_baselines
        assert baselines["QB"] == 11
        assert baselines["RB"] == 30
        assert baselines["WR"] == 30
        assert baselines["TE"] == 11
        assert baselines["K"] == 1
        assert baselines["DEF"] == 1

    def test_basketball_baselines(self):
        s = Settings(_env_file=None, sport="basketball")
        baselines = s.vorp_baselines
        assert baselines["PG"] == 12
        assert baselines["C"] == 10


class TestSlotMap:
    def test_sleeper_slot_map(self):
        s = Settings(_env_file=None, platform="sleeper", sport="football")
        sm = s.slot_map
        assert sm["QB"] == "QB"
        assert sm["SUPER_FLEX"] == "SUPERFLEX"
        assert sm["BN"] == "BENCH"

    def test_espn_slot_map(self):
        s = Settings(_env_file=None, platform="espn", sport="football")
        sm = s.slot_map
        assert sm[0] == "QB"
        assert sm[2] == "RB"
        assert sm[20] == "BENCH"
