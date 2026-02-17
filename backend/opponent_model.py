"""
Opponent modeling — tracks what positions each opponent still needs
based on roster data from DraftUpdate payloads.
Identifies bidding war scenarios and surfaces demand data.
"""

from typing import Optional
from config import settings


class OpponentTracker:
    """Tracks opponent rosters and computes positional needs."""

    def __init__(self):
        # team_key -> {position: count_drafted}
        self.team_rosters: dict[str, dict[str, int]] = {}
        # team_key -> remaining_budget
        self.team_budgets: dict[str, int] = {}
        # team_key -> roster_size
        self.team_sizes: dict[str, int] = {}
        # team_id -> team_name (for correlating with budget display names)
        self.team_names: dict[str, str] = {}

    def update_from_rosters(
        self,
        rosters: dict,
        teams: list,
        my_team_name: str,
    ):
        """Process roster data from a DraftUpdate payload."""
        # Build team_id -> team info mapping
        team_map = {}
        for t in teams:
            tid = t.teamId if hasattr(t, "teamId") else t.get("teamId")
            name = t.name if hasattr(t, "name") else t.get("name", "Unknown")
            budget = t.remainingBudget if hasattr(t, "remainingBudget") else t.get("remainingBudget")
            rsize = t.rosterSize if hasattr(t, "rosterSize") else t.get("rosterSize")
            if tid is not None:
                team_map[str(tid)] = {"name": name, "budget": budget, "rosterSize": rsize}

        for team_id_str, entries in rosters.items():
            info = team_map.get(team_id_str, {})
            team_name = info.get("name", f"Team #{team_id_str}")

            # Skip my own team (my_team_name may be comma-separated aliases)
            my_aliases = [a.strip().lower() for a in my_team_name.split(",")]
            if team_name and team_name.lower().strip() in my_aliases:
                continue

            pos_counts: dict[str, int] = {}
            for entry in entries:
                if isinstance(entry, dict):
                    pos_id = entry.get("position")
                else:
                    pos_id = getattr(entry, "position", None)

                # Platform-aware position resolution:
                # Sleeper sends string positions ("QB", "RB", ...); ESPN sends int slot IDs
                if pos_id is None:
                    pos = "UNK"
                elif isinstance(pos_id, str):
                    # Sleeper: use the slot map to normalize, or use the string directly
                    pos = settings.sleeper_slot_map.get(pos_id, pos_id)
                else:
                    pos = settings.espn_slot_map.get(pos_id, "UNK")
                # Skip bench/IR — only count starters
                if pos in ("BENCH", "IR", "UNK"):
                    continue
                pos_counts[pos] = pos_counts.get(pos, 0) + 1

            self.team_rosters[team_id_str] = pos_counts
            self.team_names[team_id_str] = team_name

            if info.get("budget") is not None:
                self.team_budgets[team_id_str] = info["budget"]
            if info.get("rosterSize") is not None:
                self.team_sizes[team_id_str] = info["rosterSize"]

    def get_position_demand(self, position: str, remaining_at_position: int) -> dict:
        """How many teams still need this position and what's the scarcity?"""
        max_slots = self._max_slots_for_position(position)
        teams_needing = 0

        for team_id, pos_counts in self.team_rosters.items():
            filled = pos_counts.get(position, 0)
            if filled < max_slots:
                teams_needing += 1

        remaining = max(remaining_at_position, 1)
        return {
            "teams_needing": teams_needing,
            "players_remaining": remaining_at_position,
            "scarcity_ratio": round(teams_needing / remaining, 2),
            "bidding_war_risk": teams_needing >= remaining * 0.75,
        }

    def get_team_threat_levels(self) -> list[dict]:
        """Rank opponents by 'spending power' — budget relative to roster holes."""
        threats = []
        for team_id, budget in self.team_budgets.items():
            roster_size = self.team_sizes.get(team_id, 0)
            filled = sum(self.team_rosters.get(team_id, {}).values())
            empty = max(roster_size - filled, 0) if roster_size else 0
            effective_power = budget - empty  # $1 per remaining slot
            threats.append({
                "team_id": team_id,
                "budget": budget,
                "roster_filled": filled,
                "roster_empty": empty,
                "spending_power": max(effective_power, 0),
            })
        threats.sort(key=lambda t: t["spending_power"], reverse=True)
        return threats

    def get_summary(self) -> dict:
        """Full opponent state for API endpoints."""
        return {
            "team_count": len(self.team_rosters),
            "team_rosters": self.team_rosters,
            "team_budgets": self.team_budgets,
            "team_names": self.team_names,
            "threat_levels": self.get_team_threat_levels(),
        }

    def _max_slots_for_position(self, position: str) -> int:
        """How many roster slots accept this position in a standard roster config?"""
        count = 0
        raw = [s.strip().upper() for s in settings.roster_slots.split(",")]
        for slot_type in raw:
            eligible = settings.SLOT_ELIGIBILITY.get(slot_type, [slot_type])
            if position in eligible:
                count += 1
        return count
