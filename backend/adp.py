"""
ADP (Average Draft Position / Average Auction Value) data loading and comparison.

Compares your engine FMV against market consensus auction values.
If FMV says $30 but ADP implies $45, the player will likely go for more.
"""

import csv
from pathlib import Path
from typing import Optional

from fuzzy_match import normalize_name


def load_adp_from_csv(csv_path: str) -> dict[str, float]:
    """
    Load ADP auction values from a local CSV.

    Expected columns: PlayerName, AuctionValue (or ADPValue)
    Returns: {normalized_name: auction_value}
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"  WARNING: ADP CSV not found: {csv_path}")
        return {}

    result = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("PlayerName", "").strip()
            if not name:
                continue
            value_str = row.get("AuctionValue") or row.get("ADPValue") or "0"
            try:
                value = float(value_str)
            except ValueError:
                continue
            result[normalize_name(name)] = value

    return result


def compare_fmv_to_adp(fmv: float, adp_value: Optional[float]) -> Optional[str]:
    """Return a human-readable comparison if ADP data exists."""
    if adp_value is None or adp_value <= 0:
        return None
    diff = fmv - adp_value
    if abs(diff) < 2:
        return f"ADP confirms FMV (ADP ${adp_value:.0f})"
    elif diff > 0:
        return f"FMV ${fmv:.0f} > ADP ${adp_value:.0f} — you value higher than market"
    else:
        return f"FMV ${fmv:.0f} < ADP ${adp_value:.0f} — market will likely bid higher"
