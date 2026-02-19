"""
In-memory draft state manager (Singleton).
Loads player projections from CSV, tracks draft progress, computes aggregates.
"""

import csv
import time
from pathlib import Path
from typing import Optional

from models import (
    PlayerProjection,
    PlayerState,
    Position,
    MyTeamState,
    DraftUpdate,
    DraftLogEntry,
    TeamInfo,
)
from config import settings
from fuzzy_match import NameResolver
from opponent_model import OpponentTracker


class DraftState:
    """Singleton managing all draft state in memory."""

    _instance: Optional["DraftState"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # Player data keyed by normalized name
        self.players: dict[str, PlayerState] = {}

        # Team budget tracking keyed by team name
        self.team_budgets: dict[str, int] = {}

        # My team — roster built from configurable slot list
        self.my_team = MyTeamState(
            team_name=settings.my_team_name,
            budget=settings.budget,
            total_budget=settings.budget,
            roster={slot: None for slot in settings.parsed_roster_slots},
            slot_types=settings.slot_base_type,
        )

        # Replacement-level points per position
        self.replacement_level: dict[str, float] = {}

        # Aggregates (recomputed on each update)
        self.total_remaining_aav: float = 0.0
        self.total_remaining_cash: float = 0.0
        self.inflation_factor: float = 1.0

        # Draft log from extension
        self.draft_log: list[dict] = []

        # Raw latest update for debugging / /state endpoint
        self.raw_latest: dict = {}

        # Inflation over time for charting (list of [timestamp, factor])
        self.inflation_history: list[list[float]] = []

        # Fuzzy name resolver (built after CSV load)
        self.name_resolver = NameResolver()

        # Opponent tracking
        self.opponent_tracker = OpponentTracker()

        # Newly drafted players from latest update (for ticker)
        self.newly_drafted: list[PlayerState] = []

        # Team display aliases (e.g. {"Team 1": "Alice", "Team 3": "TonyCollects"})
        self.team_aliases: dict[str, str] = {}

        # Resolved sport for auto-detect mode
        self.resolved_sport: str = settings.sport

    def resolve_sport(self, detected_sport: Optional[str]):
        """Resolve sport from extension auto-detection if config is 'auto'."""
        if self.resolved_sport not in ("auto", ""):
            return  # Already resolved or explicitly set
        if detected_sport and detected_sport in ("football", "basketball"):
            self.resolved_sport = detected_sport
            # Re-apply sport defaults to settings
            from config import SPORT_PROFILES
            profile = SPORT_PROFILES.get(detected_sport)
            if profile:
                settings.sport = detected_sport
                if settings.roster_slots == "QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF":
                    settings.roster_slots = profile["default_roster_slots"]
                    self.my_team.roster = {slot: None for slot in settings.parsed_roster_slots}
                    self.my_team.slot_types = settings.slot_base_type
                if settings.SLOT_ELIGIBILITY == SPORT_PROFILES["football"]["slot_eligibility"]:
                    settings.SLOT_ELIGIBILITY = profile["slot_eligibility"]
                print(f"  [Auto-detect] Sport resolved to: {detected_sport}")
        else:
            self.resolved_sport = "football"

    # -----------------------------------------------------------------
    # Reset (for replay from scratch)
    # -----------------------------------------------------------------

    def reset(self):
        """Clear all draft state back to post-CSV-load defaults.
        Preserves loaded projections but resets all draft progress."""
        for ps in self.players.values():
            ps.is_drafted = False
            ps.draft_price = None
            ps.drafted_by_team = None
        self.team_budgets.clear()
        self.my_team.budget = self.my_team.total_budget
        self.my_team.roster = {slot: None for slot in settings.parsed_roster_slots}
        self.my_team.players_acquired.clear()
        self.draft_log.clear()
        self.raw_latest.clear()
        self.inflation_history.clear()
        self.newly_drafted.clear()
        self._recompute_aggregates()

    # -----------------------------------------------------------------
    # CSV Loading
    # -----------------------------------------------------------------

    def load_projections(self, csv_path: str):
        """Load player projections from CSV at startup."""
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self._load_rows(rows)

    def load_from_merged(self, rows: list[dict]):
        """Load from pre-merged projection dicts (multi-source)."""
        self._load_rows(rows)

    def _load_rows(self, rows: list[dict]):
        """Shared loader for CSV rows or merged dicts."""
        for row in rows:
            proj = PlayerProjection(
                player_name=row["PlayerName"].strip(),
                position=Position(row["Position"].strip()),
                projected_points=float(row["ProjectedPoints"]),
                baseline_aav=float(row["BaselineAAV"]),
                tier=int(row["Tier"]),
            )
            key = self._normalize_name(proj.player_name)
            self.players[key] = PlayerState(projection=proj)

        self._compute_replacement_levels()
        self._compute_vorps()
        self._recompute_aggregates()

        # Build fuzzy matching index from loaded players
        self.name_resolver.build_index(self.players)

    # -----------------------------------------------------------------
    # Name Normalization
    # -----------------------------------------------------------------

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Lowercase, strip whitespace and trailing periods."""
        return name.lower().strip().rstrip(".")

    # -----------------------------------------------------------------
    # VORP Pre-Computation
    # -----------------------------------------------------------------

    def _compute_replacement_levels(self):
        """For each position, find the Nth-ranked player's projected points."""
        by_position: dict[str, list[float]] = {}
        for ps in self.players.values():
            pos = ps.projection.position.value
            by_position.setdefault(pos, []).append(ps.projection.projected_points)

        for pos, points_list in by_position.items():
            points_list.sort(reverse=True)
            baseline_rank = settings.vorp_baselines.get(pos, 1)
            idx = min(baseline_rank - 1, len(points_list) - 1)
            self.replacement_level[pos] = points_list[idx]

    def _compute_vorps(self):
        """Pre-compute VORP for every player."""
        for ps in self.players.values():
            pos = ps.projection.position.value
            replacement = self.replacement_level.get(pos, 0.0)
            ps.vorp = max(0.0, ps.projection.projected_points - replacement)

    # -----------------------------------------------------------------
    # Aggregate Recomputation
    # -----------------------------------------------------------------

    def _recompute_aggregates(self):
        """Recompute total remaining AAV, total remaining cash, and inflation."""
        remaining_aav = sum(
            ps.projection.baseline_aav
            for ps in self.players.values()
            if not ps.is_drafted
        )
        self.total_remaining_aav = remaining_aav

        # Total remaining cash from tracked team budgets, or full league if no data yet
        if self.team_budgets:
            self.total_remaining_cash = sum(self.team_budgets.values())
        else:
            self.total_remaining_cash = settings.league_size * settings.budget

        if self.total_remaining_aav > 0:
            self.inflation_factor = self.total_remaining_cash / self.total_remaining_aav
        else:
            self.inflation_factor = 1.0

        # Track inflation over time (for dashboard charts)
        self.inflation_history.append([time.time(), self.inflation_factor])

        # Precompute VONA for all undrafted players
        self._compute_vonas()

    def _compute_vonas(self):
        """Precompute Value Over Next Available for every player."""
        from engine import calculate_vona
        for ps in self.players.values():
            if not ps.is_drafted:
                ps.vona, ps.vona_next_player = calculate_vona(ps, self)
            else:
                ps.vona = 0.0
                ps.vona_next_player = None

    # -----------------------------------------------------------------
    # Draft Event Processing
    # -----------------------------------------------------------------

    def update_from_draft_event(self, data: DraftUpdate):
        """Process an incoming extension update. Idempotent."""
        self.raw_latest = data.model_dump()

        # Snapshot currently drafted keys so we can detect new sales
        previously_drafted = {k for k, ps in self.players.items() if ps.is_drafted}

        # Update team budgets — key by teamId to avoid duplicate entries
        # when team names resolve later (e.g. Sleeper "Team 3" → "tonytran")
        new_budgets = {}
        for team in data.teams:
            name = team.name or ""
            if name in ("Unknown", "null", "undefined", "None", ""):
                name = str(team.teamId) if team.teamId else None
            if name and team.remainingBudget is not None:
                new_budgets[name] = team.remainingBudget
        if new_budgets:
            # Replace wholesale — the extension always sends the full team list
            self.team_budgets = new_budgets

        # Mark newly drafted players from the draft log
        for entry in data.draftLog:
            # Try exact match first, then fuzzy match
            name_key = self._normalize_name(entry.playerName)
            if name_key not in self.players:
                resolved = self.name_resolver.resolve(entry.playerName)
                if resolved:
                    name_key = resolved
            if name_key in self.players and not self.players[name_key].is_drafted:
                self.players[name_key].is_drafted = True
                self.players[name_key].draft_price = entry.bidAmount
                team_name = self._resolve_team_name(entry.teamId, data.teams)
                self.players[name_key].drafted_by_team = team_name

                # Track if this is my team's pick
                if team_name and self._is_my_team(team_name):
                    self._add_to_my_roster(entry, self.players[name_key])

        # Update my team's budget from the teams list
        for team in data.teams:
            if self._is_my_team(team.name):
                if team.remainingBudget is not None:
                    self.my_team.budget = team.remainingBudget

        self.draft_log = [e.model_dump() for e in data.draftLog]
        self._recompute_aggregates()

        # Detect newly drafted players for ticker
        self.newly_drafted = [
            ps for k, ps in self.players.items()
            if ps.is_drafted and k not in previously_drafted
        ]

        # Update opponent model
        if data.rosters and data.teams:
            self.opponent_tracker.update_from_rosters(
                data.rosters, data.teams, settings.my_team_name
            )

    # -----------------------------------------------------------------
    # Team Helpers
    # -----------------------------------------------------------------

    def _is_my_team(self, name: Optional[str]) -> bool:
        if not name:
            return False
        name_lower = name.lower().strip()
        # MY_TEAM_NAME can be comma-separated for aliases (e.g. "Tony's Talented Team,tonytran")
        for alias in settings.my_team_name.split(","):
            if alias.strip().lower() == name_lower:
                return True
        return False

    @staticmethod
    def _resolve_team_name(
        team_id, teams: list[TeamInfo]
    ) -> Optional[str]:
        if team_id is None or str(team_id) in ("null", "undefined", "None", ""):
            return None
        for t in teams:
            if str(t.teamId) == str(team_id):
                return t.name
        return str(team_id)

    def _add_to_my_roster(self, entry: DraftLogEntry, ps: PlayerState):
        """Slot a drafted player into the best available roster slot.
        Priority: dedicated position > flex/superflex > bench."""
        pos = ps.projection.position.value
        eligibility = settings.SLOT_ELIGIBILITY

        # Get all open slots that accept this position
        open_slots = self.my_team.open_slots_for_position(pos, eligibility)
        if not open_slots:
            return  # No room (shouldn't happen if engine is working)

        # Priority 1: Dedicated position slot (exact match)
        best_slot = None
        for slot in open_slots:
            base_type = self.my_team.slot_types.get(slot, slot.rstrip("0123456789"))
            if base_type == pos:
                best_slot = slot
                break

        # Priority 2: First non-BENCH flex slot
        if best_slot is None:
            for slot in open_slots:
                base_type = self.my_team.slot_types.get(slot, slot.rstrip("0123456789"))
                if base_type != "BENCH":
                    best_slot = slot
                    break

        # Priority 3: BENCH (last resort)
        if best_slot is None:
            best_slot = open_slots[0]

        self.my_team.roster[best_slot] = entry.playerName
        self.my_team.players_acquired.append(
            {
                "name": entry.playerName,
                "position": pos,
                "price": entry.bidAmount,
            }
        )

    # -----------------------------------------------------------------
    # Query Methods
    # -----------------------------------------------------------------

    def get_remaining_players(
        self, position: Optional[str] = None
    ) -> list[PlayerState]:
        """Return undrafted players sorted by VORP, optionally filtered by position."""
        results = [ps for ps in self.players.values() if not ps.is_drafted]
        if position:
            results = [
                ps for ps in results if ps.projection.position.value == position
            ]
        return sorted(results, key=lambda ps: ps.vorp, reverse=True)

    def get_player(self, name: str) -> Optional[PlayerState]:
        # Try exact normalized match first (fast path)
        key = self._normalize_name(name)
        if key in self.players:
            return self.players[key]

        # Fall back to fuzzy matching
        resolved_key = self.name_resolver.resolve(name)
        if resolved_key and resolved_key in self.players:
            return self.players[resolved_key]

        return None

    def get_inflation_factor(self) -> float:
        return self.inflation_factor

    def can_use_player(self, position: str) -> bool:
        """Can my team still fit a player of this position in any open slot?"""
        return self.my_team.can_still_start(position, settings.SLOT_ELIGIBILITY)

    def get_positional_need(self) -> dict[str, int]:
        """How many open slots can accept each position (including bench)?"""
        return self.my_team.positional_need_summary(settings.SLOT_ELIGIBILITY)

    def get_starter_need(self) -> dict[str, int]:
        """How many open STARTER slots can accept each position? (excludes BENCH)"""
        return self.my_team.positional_need_summary(settings.SLOT_ELIGIBILITY, exclude_bench=True)

    def apply_alias(self, name: Optional[str]) -> Optional[str]:
        """Apply team alias for display. Returns aliased name or original."""
        if not name:
            return name
        return self.team_aliases.get(name, name)

    def get_aliased_budgets(self) -> dict[str, int]:
        """Return team_budgets with aliases applied to keys."""
        return {self.apply_alias(k): v for k, v in self.team_budgets.items()}

    def get_state_summary(self) -> dict:
        """JSON-serializable summary for the /state endpoint."""
        drafted_count = sum(1 for ps in self.players.values() if ps.is_drafted)
        return {
            "total_players": len(self.players),
            "drafted": drafted_count,
            "remaining": len(self.players) - drafted_count,
            "inflation_factor": round(self.inflation_factor, 3),
            "total_remaining_cash": self.total_remaining_cash,
            "total_remaining_aav": round(self.total_remaining_aav, 1),
            "my_team": self.my_team.model_dump(),
            "positional_need": self.get_positional_need(),
            "roster_config": settings.roster_slots,
            "team_budgets": self.get_aliased_budgets(),
            "team_aliases": self.team_aliases,
            "draft_log_length": len(self.draft_log),
        }
