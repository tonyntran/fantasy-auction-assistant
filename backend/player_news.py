"""Player news/status from Sleeper API.

Extracts team, depth chart, injury, and recent news context
from the Sleeper player database for auction draft decision-making.
"""
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

_player_db: dict = {}
_name_index: dict[str, dict] = {}  # full_name.lower() → player info (O(1) lookup)
_last_fetch: float = 0
_CACHE_TTL = 1800  # 30 minutes

# How recently news_updated must be to flag as "recent news"
_NEWS_RECENCY_HOURS = 72

SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"


def _build_name_index(db: dict) -> dict[str, dict]:
    """Build a name-indexed lookup from the Sleeper player database.

    Maps full_name.lower() -> player info dict.  When multiple players
    share the same name, prefer the entry that is active and has a team
    assignment (i.e. the fantasy-relevant one).
    """
    index: dict[str, dict] = {}
    for pid, info in db.items():
        if not isinstance(info, dict):
            continue
        full = info.get("full_name")
        if not full:
            continue
        key = full.lower()
        existing = index.get(key)
        if existing is None:
            index[key] = info
        else:
            # Resolve duplicates: prefer active player with a team
            new_score = (bool(info.get("active")), bool(info.get("team")))
            old_score = (bool(existing.get("active")), bool(existing.get("team")))
            if new_score > old_score:
                index[key] = info
    return index


async def _fetch_players():
    global _player_db, _name_index, _last_fetch
    async with httpx.AsyncClient() as client:
        resp = await client.get(SLEEPER_PLAYERS_URL, timeout=30.0)
        resp.raise_for_status()
    _player_db = resp.json()
    _name_index = _build_name_index(_player_db)
    _last_fetch = time.time()


async def ensure_loaded():
    """Fetch the Sleeper player database if cache is stale."""
    if time.time() - _last_fetch > _CACHE_TTL:
        try:
            await _fetch_players()
        except Exception as e:
            print(f"  [PlayerNews] Failed to fetch Sleeper data: {e}")


def _find_player(player_name: str) -> Optional[dict]:
    """Look up a player by name in the Sleeper database.
    When multiple players share a name, prefer active fantasy-relevant players.

    Uses a pre-built name index for O(1) exact-match lookup.  Falls back
    to a linear scan if the index misses (e.g. alternate name formats).
    """
    name_lower = player_name.lower().strip()

    # Fast path: O(1) index lookup (handles duplicate-name resolution at build time)
    hit = _name_index.get(name_lower)
    if hit is not None:
        return hit

    # Slow fallback: linear scan for partial matches or names not in the index
    matches = []
    for pid, info in _player_db.items():
        if not isinstance(info, dict):
            continue
        full = info.get("full_name", "")
        if full and full.lower() == name_lower:
            matches.append(info)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Prefer active players over inactive
    active = [m for m in matches if m.get("active")]
    if active:
        return active[0]
    return matches[0]


def get_player_status(player_name: str) -> Optional[dict]:
    """Look up injury/status for a player by name.
    Returns only if there's an injury designation."""
    info = _find_player(player_name)
    if not info:
        return None
    status = info.get("injury_status")
    if not status and info.get("active"):
        return None  # Healthy, no injury news
    return {
        "status": status or "Active",
        "injury": info.get("injury_body_part"),
        "injury_note": info.get("injury_notes"),
        "active": info.get("active", True),
    }


def get_player_context(player_name: str) -> Optional[dict]:
    """Full player context: team, depth chart, injury, and recent news flag.
    Returns info for any player with notable context (not just injured ones)."""
    info = _find_player(player_name)
    if not info:
        return None

    team = info.get("team")
    injury_status = info.get("injury_status")
    depth_chart_order = info.get("depth_chart_order")
    depth_chart_pos = info.get("depth_chart_position")
    active = info.get("active", True)
    news_updated = info.get("news_updated")  # millisecond timestamp

    # Check if there's been recent news
    has_recent_news = False
    if news_updated:
        news_age_hours = (time.time() * 1000 - news_updated) / (1000 * 3600)
        has_recent_news = news_age_hours < _NEWS_RECENCY_HOURS

    # Only return if there's something notable to show
    has_injury = bool(injury_status)
    has_notable = has_injury or has_recent_news or not active

    if not has_notable:
        return None

    result = {
        "team": team,
        "active": active,
    }

    if injury_status:
        result["injury_status"] = injury_status
        result["injury"] = info.get("injury_body_part")
        result["injury_note"] = info.get("injury_notes")

    if depth_chart_order is not None:
        result["depth_chart_order"] = depth_chart_order
    if depth_chart_pos:
        result["depth_chart_position"] = depth_chart_pos

    if news_updated:
        # Convert millisecond timestamp to ISO date and epoch seconds for sorting
        result["news_updated"] = round(news_updated / 1000)
        try:
            dt = datetime.fromtimestamp(news_updated / 1000, tz=timezone.utc)
            result["news_date"] = dt.strftime("%b %d, %Y")
        except (OSError, ValueError):
            result["news_date"] = None

    if has_recent_news:
        result["recent_news"] = True

    if not active:
        result["status"] = info.get("status", "Inactive")

    # Build a human-readable summary
    result["summary"] = _build_summary(result)

    return result


def _build_summary(ctx: dict) -> str:
    """Build a short readable summary from player context."""
    parts = []

    team = ctx.get("team")
    if team:
        dc_order = ctx.get("depth_chart_order")
        dc_pos = ctx.get("depth_chart_position")
        if dc_order and dc_pos:
            parts.append(f"{team} depth chart #{dc_order} ({dc_pos})")
        elif dc_order:
            parts.append(f"{team} depth chart #{dc_order}")
        else:
            parts.append(team)
    elif not ctx.get("active"):
        parts.append("Free agent / unsigned")

    if ctx.get("injury_status"):
        injury_detail = ctx["injury_status"]
        if ctx.get("injury"):
            injury_detail += f" ({ctx['injury']})"
        if ctx.get("injury_note"):
            injury_detail += f" — {ctx['injury_note']}"
        parts.append(injury_detail)

    if ctx.get("recent_news") and not ctx.get("injury_status"):
        parts.append("Recent news activity")

    if not ctx.get("active") and not ctx.get("injury_status"):
        parts.append(ctx.get("status", "Inactive"))

    return ". ".join(parts) if parts else ""


def get_player_roster_info(player_name: str) -> dict:
    """Get team abbreviation and bye week for any player (for roster display).

    Bye week is sourced from the Sleeper player metadata, which is
    updated each season automatically.  If Sleeper does not have a
    bye_week for a player, it is simply omitted rather than showing
    stale data from a previous season.
    """
    info = _find_player(player_name)
    if not info:
        return {}
    team = info.get("team")
    result = {}
    if team:
        result["team"] = team
        # Prefer metadata.bye_week (populated by Sleeper per-season)
        meta = info.get("metadata") or {}
        bye = meta.get("bye_week")
        if bye is not None:
            result["bye_week"] = int(bye)
    return result


def get_news_for_undrafted(state) -> dict:
    """Return context info for all undrafted players with notable news."""
    news_map = {}
    for ps in state.players.values():
        if ps.is_drafted:
            continue
        context = get_player_context(ps.projection.player_name)
        if context:
            news_map[ps.projection.player_name] = context
    return news_map
