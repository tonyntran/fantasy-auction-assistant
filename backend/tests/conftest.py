"""
Shared pytest fixtures for the Fantasy Auction Assistant backend test suite.
"""

import csv
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the backend directory is on sys.path so we can import modules directly
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# =====================================================================
# Singleton Reset Fixture (autouse)
# =====================================================================

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests to ensure isolation."""
    from state import DraftState
    from ticker import TickerBuffer
    from event_store import EventStore

    DraftState._reset_for_testing()
    TickerBuffer._reset_for_testing()
    EventStore._reset_for_testing()

    yield

    DraftState._reset_for_testing()
    TickerBuffer._reset_for_testing()
    EventStore._reset_for_testing()


# =====================================================================
# Override settings to stable test defaults
# =====================================================================

@pytest.fixture(autouse=True)
def _test_settings():
    """Override settings to ensure consistent test defaults regardless of .env."""
    from config import settings

    from config import SPORT_PROFILES

    original_values = {
        "platform": settings.platform,
        "sport": settings.sport,
        "ai_provider": settings.ai_provider,
        "my_team_name": settings.my_team_name,
        "league_size": settings.league_size,
        "budget": settings.budget,
        "roster_slots": settings.roster_slots,
        "draft_strategy": settings.draft_strategy,
        "csv_path": settings.csv_path,
        "event_log_path": settings.event_log_path,
        "SLOT_ELIGIBILITY": dict(settings.SLOT_ELIGIBILITY),
    }

    # Set stable test defaults
    settings.platform = "sleeper"
    settings.sport = "football"
    settings.ai_provider = "claude"
    settings.my_team_name = "My Team"
    settings.league_size = 10
    settings.budget = 200
    settings.roster_slots = "QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF"
    settings.draft_strategy = "balanced"
    settings.SLOT_ELIGIBILITY = SPORT_PROFILES["football"]["slot_eligibility"]

    yield settings

    # Restore originals
    for key, val in original_values.items():
        setattr(settings, key, val)


# =====================================================================
# Sample CSV Data
# =====================================================================

SAMPLE_PLAYERS = [
    # PlayerName, Position, ProjectedPoints, BaselineAAV, Tier
    ("Patrick Mahomes", "QB", 380.0, 25.0, 1),
    ("Josh Allen", "QB", 370.0, 22.0, 1),
    ("Jalen Hurts", "QB", 340.0, 15.0, 2),
    ("Lamar Jackson", "QB", 330.0, 13.0, 2),
    ("Saquon Barkley", "RB", 280.0, 55.0, 1),
    ("Breece Hall", "RB", 260.0, 45.0, 1),
    ("Bijan Robinson", "RB", 250.0, 42.0, 1),
    ("Derrick Henry", "RB", 220.0, 30.0, 2),
    ("CeeDee Lamb", "WR", 300.0, 50.0, 1),
    ("Ja'Marr Chase", "WR", 290.0, 48.0, 1),
    ("Tyreek Hill", "WR", 270.0, 40.0, 2),
    ("Davante Adams", "WR", 240.0, 28.0, 2),
    ("Travis Kelce", "TE", 230.0, 35.0, 1),
    ("Mark Andrews", "TE", 190.0, 15.0, 2),
    ("Tyler Bass", "K", 140.0, 1.0, 1),
    ("Dallas Cowboys", "DEF", 120.0, 2.0, 1),
]


@pytest.fixture
def sample_csv_data():
    """Return the raw sample player data as a list of tuples."""
    return SAMPLE_PLAYERS


@pytest.fixture
def sample_csv_rows():
    """Return sample data as list of dicts matching CSV DictReader output."""
    return [
        {
            "PlayerName": name,
            "Position": pos,
            "ProjectedPoints": str(pts),
            "BaselineAAV": str(aav),
            "Tier": str(tier),
        }
        for name, pos, pts, aav, tier in SAMPLE_PLAYERS
    ]


@pytest.fixture
def sample_csv_file(tmp_path, sample_csv_data):
    """Write sample data to a temporary CSV file and return the path."""
    csv_path = tmp_path / "test_projections.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["PlayerName", "Position", "ProjectedPoints", "BaselineAAV", "Tier"])
        for row in sample_csv_data:
            writer.writerow(row)
    return str(csv_path)


# =====================================================================
# DraftState Fixture
# =====================================================================

@pytest.fixture
def draft_state(sample_csv_file):
    """Create a DraftState instance loaded with sample CSV data."""
    from state import DraftState
    state = DraftState()
    state.load_projections(sample_csv_file)
    return state


# =====================================================================
# Sample DraftUpdate Payload
# =====================================================================

@pytest.fixture
def sample_draft_update():
    """Return a dict matching the DraftUpdate payload shape."""
    return {
        "timestamp": 1700000000,
        "currentNomination": {
            "playerId": "12345",
            "playerName": "Patrick Mahomes",
            "nominatingTeamId": "1",
        },
        "currentBid": 30.0,
        "highBidder": "Team Alpha",
        "teams": [
            {
                "teamId": "1",
                "name": "Team Alpha",
                "totalBudget": 200,
                "remainingBudget": 170,
                "rosterSize": 10,
            },
            {
                "teamId": "2",
                "name": "My Team",
                "totalBudget": 200,
                "remainingBudget": 200,
                "rosterSize": 10,
            },
            {
                "teamId": "3",
                "name": "Team Gamma",
                "totalBudget": 200,
                "remainingBudget": 180,
                "rosterSize": 10,
            },
        ],
        "draftLog": [
            {
                "playerId": "12345",
                "playerName": "Patrick Mahomes",
                "teamId": "1",
                "bidAmount": 30,
                "keeper": False,
            },
        ],
        "rosters": {},
        "source": "test",
        "sport": "football",
        "platform": "sleeper",
    }
