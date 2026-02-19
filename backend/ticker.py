"""
Live Bid Ticker — rolling event buffer for real-time draft activity feed.

Tracks nominations, bids, sales, budget alerts, and market shifts.
Events are pushed to both the overlay and the web dashboard.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from models import DraftUpdate

class TickerEventType(str, Enum):
    NEW_NOMINATION = "NEW_NOMINATION"
    BID_PLACED = "BID_PLACED"
    PLAYER_SOLD = "PLAYER_SOLD"
    BUDGET_ALERT = "BUDGET_ALERT"
    MARKET_SHIFT = "MARKET_SHIFT"


class TickerEvent(BaseModel):
    event_type: TickerEventType
    timestamp: float
    message: str
    player_name: Optional[str] = None
    team_name: Optional[str] = None
    amount: Optional[float] = None
    details: Optional[dict] = None


class TickerBuffer:
    """Singleton rolling buffer of the most recent draft events."""

    _instance: Optional["TickerBuffer"] = None
    MAX_EVENTS = 50

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.events: list[TickerEvent] = []
        self._last_nomination: Optional[str] = None
        self._last_bid: Optional[tuple] = None

    def push(self, event: TickerEvent):
        """Append an event, evict oldest if buffer is full."""
        self.events.append(event)
        if len(self.events) > self.MAX_EVENTS:
            self.events = self.events[-self.MAX_EVENTS:]

    def get_recent(self, n: int = 20) -> list[dict]:
        """Return the most recent N events as dicts, oldest first (chat order)."""
        return [e.model_dump() for e in self.events[-n:]]

    def process_update(self, data: "DraftUpdate"):
        """
        Detect new nominations and bid changes from an incoming DraftUpdate.
        Called from /draft_update before sale processing.
        """
        now = time.time()

        # Detect new nomination
        if data.currentNomination:
            nom_name = data.currentNomination.playerName
            if nom_name and nom_name != self._last_nomination:
                self._last_nomination = nom_name
                self._last_bid = None
                team_label = _resolve_team(data.currentNomination.nominatingTeamId, data.teams)
                self.push(TickerEvent(
                    event_type=TickerEventType.NEW_NOMINATION,
                    timestamp=now,
                    message=f"{team_label} nominated {nom_name}",
                    player_name=nom_name,
                    team_name=team_label,
                ))

        # Detect bid changes
        if data.currentNomination and data.currentBid is not None:
            bid_key = (
                data.currentNomination.playerName,
                data.currentBid,
                str(data.highBidder) if data.highBidder else None,
            )
            if bid_key != self._last_bid:
                self._last_bid = bid_key
                bidder = str(data.highBidder) if data.highBidder else "Unknown"
                player_name = data.currentNomination.playerName
                amount = data.currentBid

                self.push(TickerEvent(
                    event_type=TickerEventType.BID_PLACED,
                    timestamp=now,
                    message=f"{bidder} bid ${int(amount)} on {player_name}",
                    player_name=player_name,
                    team_name=bidder,
                    amount=amount,
                ))


def _resolve_team(team_id, teams) -> str:
    """Resolve a team ID to a display name."""
    if team_id is None:
        return "Unknown"
    for t in teams:
        if str(t.teamId) == str(team_id):
            return t.name or t.abbrev or f"Team #{team_id}"
    return f"Team #{team_id}"
