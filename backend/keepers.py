"""
Keeper league support -- pre-draft player assignments.

CSV format: PlayerName,Team,Price
Example:
  Josh Allen,Team Alpha,45
  Bijan Robinson,Team Beta,38
"""

import csv
from pathlib import Path

from config import settings
from state import DraftState


def load_keepers(state: DraftState) -> list[dict]:
    """Load keepers from CSV and apply them to draft state.

    Returns list of keeper records for logging.
    """
    csv_path = settings.keepers_csv
    if not csv_path or not Path(csv_path).exists():
        return []

    keepers: list[dict] = []
    seen_names: set[str] = set()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate required columns
        if reader.fieldnames is None or not all(
            col in reader.fieldnames for col in ("PlayerName", "Team", "Price")
        ):
            print(
                "[Keepers] ERROR: CSV must have columns: PlayerName, Team, Price"
            )
            return []

        for row in reader:
            name = row["PlayerName"].strip()
            team = row["Team"].strip()
            try:
                price = int(row["Price"])
            except (ValueError, TypeError):
                print(f"[Keepers] Warning: Invalid price for '{name}', skipping")
                continue

            if not name or not team:
                continue

            # Duplicate check
            name_lower = name.lower()
            if name_lower in seen_names:
                print(f"[Keepers] Warning: Duplicate keeper '{name}', skipping")
                continue
            seen_names.add(name_lower)

            player = state.get_player(name)
            if not player:
                print(
                    f"[Keepers] Warning: '{name}' not found in projections, skipping"
                )
                continue
            if player.is_drafted:
                print(f"[Keepers] Warning: '{name}' already drafted, skipping")
                continue

            # Mark as drafted keeper
            actual_name = player.projection.player_name
            pos = player.projection.position.value
            player.is_drafted = True
            player.draft_price = price
            player.drafted_by_team = team
            player.is_keeper = True

            # Update team budget
            if team in state.team_budgets:
                state.team_budgets[team] -= price
            else:
                state.team_budgets[team] = settings.budget - price

            # If it's my team, update roster
            if state._is_my_team(team):
                open_slots = state.my_team.open_slots_for_position(
                    pos, settings.SLOT_ELIGIBILITY
                )
                if open_slots:
                    # Priority: dedicated position > flex > bench
                    best_slot = None
                    for slot in open_slots:
                        base_type = state.my_team.slot_types.get(
                            slot, slot.rstrip("0123456789")
                        )
                        if base_type == pos:
                            best_slot = slot
                            break
                    if best_slot is None:
                        for slot in open_slots:
                            base_type = state.my_team.slot_types.get(
                                slot, slot.rstrip("0123456789")
                            )
                            if base_type not in ("BENCH",):
                                best_slot = slot
                                break
                    if best_slot is None:
                        best_slot = open_slots[0]
                    state.my_team.roster[best_slot] = actual_name

                state.my_team.budget -= price
                state.my_team.players_acquired.append(
                    {
                        "name": actual_name,
                        "position": pos,
                        "price": price,
                        "is_keeper": True,
                    }
                )

            keepers.append(
                {
                    "player": actual_name,
                    "team": team,
                    "price": price,
                    "position": pos,
                }
            )
            print(f"[Keepers] {actual_name} kept by {team} for ${price}")

    # Recompute aggregates after all keepers applied
    if keepers:
        state._recompute_aggregates()

    return keepers
