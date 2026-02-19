"""
Application settings loaded from .env file via pydantic-settings.
Supports multiple sports (football, basketball) via SPORT_PROFILES.
"""

from pydantic_settings import BaseSettings
from pydantic import model_validator


# -----------------------------------------------------------------
# Sport-specific profiles
# -----------------------------------------------------------------

SPORT_PROFILES = {
    "football": {
        "positions": ["QB", "RB", "WR", "TE", "K", "DEF"],
        "display_positions": ["QB", "RB", "WR", "TE"],
        "default_roster_slots": "QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF",
        "season_games": 17,
        "slot_eligibility": {
            "QB": ["QB"], "RB": ["RB"], "WR": ["WR"], "TE": ["TE"],
            "K": ["K"], "DEF": ["DEF"],
            "FLEX": ["RB", "WR", "TE"],
            "SUPERFLEX": ["QB", "RB", "WR", "TE"],
            "BENCH": ["QB", "RB", "WR", "TE", "K", "DEF"],
        },
        "vorp_baselines": {"QB": 11, "RB": 30, "WR": 30, "TE": 11, "K": 1, "DEF": 1},
        "espn_slot_map": {
            0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DEF", 17: "K",
            20: "BENCH", 21: "IR", 23: "FLEX",
        },
        "sleeper_slot_map": {
            "QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE",
            "K": "K", "DEF": "DEF", "FLEX": "FLEX", "SUPER_FLEX": "SUPERFLEX",
            "BN": "BENCH", "IR": "IR",
        },
        "sport_name": "football",
        "position_badges": {
            "QB": "badge-error", "RB": "badge-success", "WR": "badge-info",
            "TE": "badge-warning", "K": "badge-ghost", "DEF": "badge-accent",
        },
    },
    "basketball": {
        "positions": ["PG", "SG", "SF", "PF", "C"],
        "display_positions": ["PG", "SG", "SF", "PF", "C"],
        "default_roster_slots": "PG,SG,G,SF,PF,F,C,UTIL,UTIL,UTIL",
        "season_games": 82,
        "slot_eligibility": {
            "PG": ["PG"], "SG": ["SG"], "SF": ["SF"], "PF": ["PF"], "C": ["C"],
            "G": ["PG", "SG"], "F": ["SF", "PF"],
            "UTIL": ["PG", "SG", "SF", "PF", "C"],
        },
        "vorp_baselines": {"PG": 12, "SG": 12, "SF": 12, "PF": 12, "C": 10},
        "espn_slot_map": {
            0: "PG", 1: "SG", 2: "G", 3: "SF", 4: "PF", 5: "F", 6: "C",
            7: "UTIL", 11: "BENCH", 12: "IR",
        },
        "sleeper_slot_map": {
            "PG": "PG", "SG": "SG", "SF": "SF", "PF": "PF", "C": "C",
            "G": "G", "F": "F", "UTIL": "UTIL",
            "BN": "BENCH", "IR": "IR",
        },
        "sport_name": "basketball",
        "position_badges": {
            "PG": "badge-error", "SG": "badge-warning", "SF": "badge-info",
            "PF": "badge-success", "C": "badge-accent",
        },
    },
}

# -----------------------------------------------------------------
# Draft strategy profiles
# -----------------------------------------------------------------

DRAFT_STRATEGIES = {
    "balanced": {
        "label": "Balanced",
        "description": "No positional bias — pure value drafting",
        "position_weights": {},
        "tier_weights": {},
    },
    "studs_and_steals": {
        "label": "Studs & Steals",
        "description": "Pay premium for 2-3 elite starters, then hunt steals — players below FMV with upside catalysts",
        "position_weights": {},
        "tier_weights": {1: 1.15, 2: 1.05, 3: 0.92, 4: 0.85, 5: 0.80},
    },
    "rb_heavy": {
        "label": "RB Heavy",
        "description": "Prioritize running backs — pay premium for top RBs",
        "position_weights": {"RB": 1.3, "QB": 0.9, "WR": 0.95, "TE": 0.9},
        "tier_weights": {},
    },
    "wr_heavy": {
        "label": "WR Heavy",
        "description": "Prioritize wide receivers — pay premium for top WRs",
        "position_weights": {"WR": 1.3, "QB": 0.9, "RB": 0.95, "TE": 0.9},
        "tier_weights": {},
    },
    "elite_te": {
        "label": "Elite TE",
        "description": "Pay premium for a top-tier tight end",
        "position_weights": {"TE": 1.35, "QB": 0.95, "RB": 0.95, "WR": 0.95},
        "tier_weights": {1: 1.2, 2: 1.1},
    },
}

_FOOTBALL_ROSTER_DEFAULT = "QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF"
_FOOTBALL_ELIGIBILITY = SPORT_PROFILES["football"]["slot_eligibility"]


class Settings(BaseSettings):
    # Platform selection: "espn" or "sleeper"
    platform: str = "espn"

    # Sport selection: "football", "basketball", or "auto" (detect from extension URL)
    sport: str = "football"

    # AI provider: "gemini" or "claude"
    ai_provider: str = "gemini"

    # API keys
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    espn_swid: str = ""
    espn_s2: str = ""

    # Sleeper-specific configuration
    sleeper_league_id: str = ""
    sleeper_draft_id: str = ""

    # League configuration
    my_team_name: str = "My Team"
    league_size: int = 10
    budget: int = 200

    # Roster slots — comma-separated string, parsed into structured data below.
    roster_slots: str = _FOOTBALL_ROSTER_DEFAULT

    # Data
    csv_path: str = "data/sheet_2026.csv"
    event_log_path: str = "data/event_log.jsonl"

    # Multi-source projections (comma-separated CSV paths; empty = use csv_path only)
    csv_paths: str = ""
    projection_weights: str = ""

    # Draft strategy
    draft_strategy: str = "balanced"

    # ADP comparison (path to ADP CSV; empty = disabled)
    adp_csv_path: str = ""

    # AI settings
    gemini_model: str = "gemini-2.5-flash"
    claude_model: str = "claude-haiku-4-5-20251001"
    ai_timeout_ms: int = 8000

    # VORP replacement-level ranks per position — football
    vorp_baseline_qb: int = 11
    vorp_baseline_rb: int = 30
    vorp_baseline_wr: int = 30
    vorp_baseline_te: int = 11
    vorp_baseline_k: int = 1
    vorp_baseline_def: int = 1

    # VORP replacement-level ranks per position — basketball
    vorp_baseline_pg: int = 12
    vorp_baseline_sg: int = 12
    vorp_baseline_sf: int = 12
    vorp_baseline_pf: int = 12
    vorp_baseline_c: int = 10

    # Which positions each slot type accepts (overridden by sport profile if not customized)
    SLOT_ELIGIBILITY: dict[str, list[str]] = _FOOTBALL_ELIGIBILITY

    @model_validator(mode="after")
    def _apply_sport_defaults(self):
        """Override roster_slots and SLOT_ELIGIBILITY when sport != football
        and the user hasn't set custom values in .env."""
        if self.sport not in ("football", "auto"):
            profile = SPORT_PROFILES.get(self.sport)
            if profile:
                if self.roster_slots == _FOOTBALL_ROSTER_DEFAULT:
                    self.roster_slots = profile["default_roster_slots"]
                if self.SLOT_ELIGIBILITY == _FOOTBALL_ELIGIBILITY:
                    self.SLOT_ELIGIBILITY = profile["slot_eligibility"]
        return self

    # -----------------------------------------------------------------
    # Sport-derived properties
    # -----------------------------------------------------------------

    @property
    def active_strategy(self) -> dict:
        return DRAFT_STRATEGIES.get(self.draft_strategy, DRAFT_STRATEGIES["balanced"])

    @property
    def sport_profile(self) -> dict:
        effective = self.sport if self.sport != "auto" else "football"
        return SPORT_PROFILES.get(effective, SPORT_PROFILES["football"])

    @property
    def positions(self) -> list[str]:
        return self.sport_profile["positions"]

    @property
    def display_positions(self) -> list[str]:
        return self.sport_profile["display_positions"]

    @property
    def espn_slot_map(self) -> dict[int, str]:
        return self.sport_profile["espn_slot_map"]

    @property
    def sleeper_slot_map(self) -> dict[str, str]:
        return self.sport_profile["sleeper_slot_map"]

    @property
    def slot_map(self) -> dict:
        """Return the appropriate slot mapping based on the active platform."""
        if self.platform.lower() == "sleeper":
            return self.sleeper_slot_map
        return self.espn_slot_map

    @property
    def sport_name(self) -> str:
        return self.sport_profile["sport_name"]

    @property
    def season_games(self) -> int:
        return self.sport_profile.get("season_games", 17)

    # -----------------------------------------------------------------
    # Roster parsing
    # -----------------------------------------------------------------

    @property
    def parsed_roster_slots(self) -> list[str]:
        """Parse the comma-separated roster_slots string into a list of labeled slot names.
        Duplicates get numbered: RB -> RB1, RB2. Single slots stay as-is: QB, TE."""
        raw = [s.strip().upper() for s in self.roster_slots.split(",") if s.strip()]
        counts: dict[str, int] = {}
        labeled: list[str] = []
        # Count occurrences first
        for slot in raw:
            counts[slot] = counts.get(slot, 0) + 1
        # Now label
        seen: dict[str, int] = {}
        for slot in raw:
            seen[slot] = seen.get(slot, 0) + 1
            if counts[slot] > 1:
                labeled.append(f"{slot}{seen[slot]}")
            else:
                labeled.append(slot)
        return labeled

    @property
    def roster_size(self) -> int:
        return len(self.parsed_roster_slots)

    @property
    def slot_base_type(self) -> dict[str, str]:
        """Map labeled slot names back to their base type. E.g. 'RB2' -> 'RB', 'FLEX1' -> 'FLEX'."""
        result = {}
        for label in self.parsed_roster_slots:
            # Strip trailing digits to get base type
            base = label.rstrip("0123456789")
            result[label] = base
        return result

    @property
    def vorp_baselines(self) -> dict[str, int]:
        profile = self.sport_profile
        defaults = profile["vorp_baselines"]
        result = {}
        for pos, default_val in defaults.items():
            env_key = f"vorp_baseline_{pos.lower()}"
            override = getattr(self, env_key, None)
            if override is not None:
                result[pos] = override
            else:
                result[pos] = default_val
        return result

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
