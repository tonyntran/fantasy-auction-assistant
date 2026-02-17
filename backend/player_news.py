"""Player news/status from Sleeper API."""
import asyncio
import time
from typing import Optional

import httpx

_player_db: dict = {}
_last_fetch: float = 0
_CACHE_TTL = 1800  # 30 minutes

SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"


async def _fetch_players():
    global _player_db, _last_fetch
    async with httpx.AsyncClient() as client:
        resp = await client.get(SLEEPER_PLAYERS_URL, timeout=30.0)
        resp.raise_for_status()
    _player_db = resp.json()
    _last_fetch = time.time()


async def ensure_loaded():
    """Fetch the Sleeper player database if cache is stale."""
    if time.time() - _last_fetch > _CACHE_TTL:
        try:
            await _fetch_players()
        except Exception as e:
            print(f"  [PlayerNews] Failed to fetch Sleeper data: {e}")


def get_player_status(player_name: str) -> Optional[dict]:
    """Look up injury/status for a player by name."""
    name_lower = player_name.lower().strip()
    for pid, info in _player_db.items():
        if not isinstance(info, dict):
            continue
        full = info.get("full_name", "")
        if full and full.lower() == name_lower:
            status = info.get("injury_status")  # "Questionable", "Out", "IR", "Doubtful", etc.
            if not status and info.get("active"):
                return None  # Healthy, no news
            return {
                "status": status or "Active",
                "injury": info.get("injury_body_part"),
                "injury_note": info.get("injury_notes"),
                "active": info.get("active", True),
            }
    return None


def get_news_for_undrafted(state) -> dict:
    """Return injury/status info for all undrafted players that have news."""
    news_map = {}
    for ps in state.players.values():
        if ps.is_drafted:
            continue
        news = get_player_status(ps.projection.player_name)
        if news:
            news_map[ps.projection.player_name] = news
    return news_map
