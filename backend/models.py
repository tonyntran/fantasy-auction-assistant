"""
Pydantic models for the Fantasy Auction Assistant.
Defines incoming data shapes, player projections, team state, and advice output.
"""

from pydantic import BaseModel
from typing import Optional, Any
from enum import Enum


# =====================================================================
# Incoming from Chrome Extension
# =====================================================================

class NominationInfo(BaseModel):
    playerId: Optional[Any] = None  # int for ESPN, str for Sleeper
    playerName: str = "Unknown"
    nominatingTeamId: Optional[Any] = None

    class Config:
        extra = "allow"


class TeamInfo(BaseModel):
    teamId: Optional[Any] = None  # int for ESPN, str/int for Sleeper
    name: str = "Unknown"
    abbrev: Optional[str] = None
    totalBudget: int = 200
    remainingBudget: Optional[int] = None
    rosterSize: Optional[int] = None

    class Config:
        extra = "allow"


class DraftLogEntry(BaseModel):
    playerId: Optional[Any] = None  # int for ESPN, str for Sleeper
    playerName: str = "Unknown"
    teamId: Optional[Any] = None  # int for ESPN, str/int for Sleeper roster_id
    bidAmount: int = 0
    roundId: Optional[int] = None
    roundPickNumber: Optional[int] = None
    keeper: bool = False

    class Config:
        extra = "allow"


class RosterEntry(BaseModel):
    playerId: Optional[Any] = None
    playerName: str = "Unknown"
    position: Optional[Any] = None  # int for ESPN slot IDs, str for Sleeper position names
    acquisitionType: Optional[str] = None

    class Config:
        extra = "allow"


class AuthInfo(BaseModel):
    # ESPN
    swid: Optional[str] = None
    espn_s2: Optional[str] = None
    # Sleeper
    sleeper_league_id: Optional[str] = None
    sleeper_draft_id: Optional[str] = None

    class Config:
        extra = "allow"


class DraftUpdate(BaseModel):
    """Incoming payload from the Chrome extension. Must remain backward-compatible."""
    timestamp: Optional[int] = None
    currentNomination: Optional[NominationInfo] = None
    currentBid: Optional[float] = None
    highBidder: Any = None
    teams: list[TeamInfo] = []
    draftLog: list[DraftLogEntry] = []
    rosters: dict[str, list[RosterEntry]] = {}
    auth: Optional[AuthInfo] = None
    source: Optional[str] = None
    sport: Optional[str] = None
    platform: Optional[str] = None  # "espn" or "sleeper"

    class Config:
        extra = "allow"


# =====================================================================
# Player Projections (from CSV)
# =====================================================================

class Position(str, Enum):
    # Football
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"
    # Basketball
    PG = "PG"
    SG = "SG"
    SF = "SF"
    PF = "PF"
    C = "C"


class PlayerProjection(BaseModel):
    player_name: str
    position: Position
    projected_points: float
    baseline_aav: float
    tier: int


class PlayerState(BaseModel):
    """A player with projection data plus live draft state."""
    projection: PlayerProjection
    is_drafted: bool = False
    draft_price: Optional[int] = None
    drafted_by_team: Optional[str] = None
    vorp: float = 0.0
    vona: float = 0.0
    vona_next_player: Optional[str] = None
    adp_value: Optional[float] = None


# =====================================================================
# My Team Tracking
# =====================================================================

class MyTeamState(BaseModel):
    team_name: str
    budget: int
    total_budget: int
    # slot_label -> player_name or None (e.g. {"QB": None, "RB1": "Saquon Barkley", ...})
    roster: dict[str, Optional[str]] = {}
    players_acquired: list[dict] = []
    # slot_label -> base_type (e.g. {"QB": "QB", "RB1": "RB", "FLEX1": "FLEX"})
    slot_types: dict[str, str] = {}

    @property
    def roster_spots_remaining(self) -> int:
        return sum(1 for v in self.roster.values() if v is None)

    @property
    def max_bid(self) -> int:
        """Budget minus $1 reserved per remaining empty slot (excluding current pick)."""
        empty = self.roster_spots_remaining
        if empty <= 1:
            return self.budget
        return self.budget - (empty - 1)

    def open_slots_for_position(self, position: str, slot_eligibility: dict[str, list[str]]) -> list[str]:
        """Return list of empty slot labels that can accept this position.
        E.g. for position='RB', might return ['RB2', 'FLEX1'] if RB1 is filled."""
        open_slots = []
        for slot_label, occupant in self.roster.items():
            if occupant is not None:
                continue
            base_type = self.slot_types.get(slot_label, slot_label.rstrip("0123456789"))
            eligible_positions = slot_eligibility.get(base_type, [base_type])
            if position in eligible_positions:
                open_slots.append(slot_label)
        return open_slots

    def can_still_start(self, position: str, slot_eligibility: dict[str, list[str]]) -> bool:
        """Can we still fit a player of this position in any open slot?"""
        return len(self.open_slots_for_position(position, slot_eligibility)) > 0

    def positional_need_summary(self, slot_eligibility: dict[str, list[str]]) -> dict[str, int]:
        """Return {position: number_of_open_slots_that_accept_it}."""
        positions = set()
        for eligible in slot_eligibility.values():
            positions.update(eligible)
        return {
            pos: len(self.open_slots_for_position(pos, slot_eligibility))
            for pos in sorted(positions)
        }


# =====================================================================
# Engine Output
# =====================================================================

class AdviceAction(str, Enum):
    BUY = "BUY"
    PASS = "PASS"
    PRICE_ENFORCE = "PRICE_ENFORCE"
    NOMINATE = "NOMINATE"


class EngineAdvice(BaseModel):
    action: AdviceAction
    max_bid: int
    fmv: float
    inflation_rate: float
    scarcity_multiplier: float
    vorp: float
    reasoning: str
    vona: float = 0.0
    vona_next_player: Optional[str] = None
    adp_value: Optional[float] = None
    adp_vs_fmv: Optional[str] = None
    opponent_demand: Optional[dict] = None


class FullAdvice(BaseModel):
    """Combined engine + AI advice returned to the extension."""
    action: AdviceAction
    max_bid: int
    fmv: float
    inflation_rate: float
    reasoning: str
    source: str = "engine"
