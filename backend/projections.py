"""
Multi-source projection merging.

Loads multiple CSV files, matches players by normalized name,
and produces weighted-average ProjectedPoints and BaselineAAV.
"""

import csv
import re
from pathlib import Path
from typing import Optional


def _normalize(name: str) -> str:
    """Aggressive normalization for cross-source player matching."""
    s = name.strip().lower()
    s = re.sub(r"[.\-'']", "", s)
    s = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv|v|2nd|3rd)$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def load_and_merge_projections(
    csv_paths: list[str],
    weights: Optional[list[float]] = None,
) -> list[dict]:
    """
    Load multiple CSVs and produce weighted-average projections.

    Each CSV must have: PlayerName, Position, ProjectedPoints, BaselineAAV, Tier
    Players are matched by normalized name. If a player appears in only some
    sources, those sources are used (missing sources are ignored, not zeroed).

    Returns list of dicts with same schema as single-source CSV rows.
    """
    if weights is None:
        weights = [1.0] * len(csv_paths)

    # player_key -> list of source records
    player_data: dict[str, list[dict]] = {}

    for path_str, weight in zip(csv_paths, weights):
        path = Path(path_str)
        if not path.exists():
            print(f"  WARNING: CSV not found, skipping: {path_str}")
            continue
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["PlayerName"].strip()
                key = _normalize(name)
                player_data.setdefault(key, []).append({
                    "weight": weight,
                    "points": float(row["ProjectedPoints"]),
                    "aav": float(row["BaselineAAV"]),
                    "position": row["Position"].strip().upper(),
                    "tier": int(row["Tier"]),
                    "name": name,
                })

    # Merge: weighted average of points and AAV
    merged = []
    for key, sources in player_data.items():
        total_weight = sum(s["weight"] for s in sources)
        avg_points = sum(s["points"] * s["weight"] for s in sources) / total_weight
        avg_aav = sum(s["aav"] * s["weight"] for s in sources) / total_weight
        # Use position/tier/name from highest-weight source
        best = max(sources, key=lambda s: s["weight"])
        merged.append({
            "PlayerName": best["name"],
            "Position": best["position"],
            "ProjectedPoints": str(round(avg_points, 1)),
            "BaselineAAV": str(round(avg_aav, 1)),
            "Tier": str(best["tier"]),
            "source_count": len(sources),
        })

    return merged
