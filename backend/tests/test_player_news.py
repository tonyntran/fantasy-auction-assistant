"""Tests for the player_news name-indexed lookup."""

import player_news


# =====================================================================
# Helpers
# =====================================================================

def _make_player(pid, full_name, active=True, team=None, status="Active"):
    """Build a minimal Sleeper-style player dict."""
    return {
        "player_id": pid,
        "full_name": full_name,
        "first_name": full_name.split()[0] if " " in full_name else full_name,
        "last_name": full_name.split()[-1] if " " in full_name else "",
        "active": active,
        "team": team,
        "status": status,
    }


def _load_db(entries: dict):
    """Inject a fake player DB and rebuild the name index."""
    player_news._player_db = entries
    player_news._name_index = player_news._build_name_index(entries)


# =====================================================================
# _build_name_index
# =====================================================================

class TestBuildNameIndex:
    def test_basic_index_creation(self):
        db = {
            "100": _make_player("100", "Patrick Mahomes", team="KC"),
            "200": _make_player("200", "Josh Allen", team="BUF"),
        }
        index = player_news._build_name_index(db)
        assert "patrick mahomes" in index
        assert "josh allen" in index
        assert index["patrick mahomes"]["player_id"] == "100"
        assert index["josh allen"]["player_id"] == "200"

    def test_duplicate_name_prefers_active_with_team(self):
        db = {
            "300": _make_player("300", "Mike Williams", active=False, team=None),
            "301": _make_player("301", "Mike Williams", active=True, team="NYJ"),
        }
        index = player_news._build_name_index(db)
        assert index["mike williams"]["player_id"] == "301"

    def test_duplicate_name_prefers_active_over_inactive(self):
        db = {
            "400": _make_player("400", "Chris Smith", active=False, team=None),
            "401": _make_player("401", "Chris Smith", active=True, team=None),
        }
        index = player_news._build_name_index(db)
        assert index["chris smith"]["player_id"] == "401"

    def test_duplicate_name_prefers_team_when_both_active(self):
        db = {
            "500": _make_player("500", "John Brown", active=True, team=None),
            "501": _make_player("501", "John Brown", active=True, team="BAL"),
        }
        index = player_news._build_name_index(db)
        assert index["john brown"]["player_id"] == "501"

    def test_skips_non_dict_entries(self):
        db = {
            "600": _make_player("600", "Player One", team="LAR"),
            "601": "not a dict",
            "602": None,
        }
        index = player_news._build_name_index(db)
        assert len(index) == 1
        assert "player one" in index

    def test_skips_entries_without_full_name(self):
        db = {
            "700": {"player_id": "700", "active": True},
            "701": {"player_id": "701", "full_name": "", "active": True},
            "702": _make_player("702", "Valid Player", team="SEA"),
        }
        index = player_news._build_name_index(db)
        assert len(index) == 1
        assert "valid player" in index

    def test_empty_db(self):
        index = player_news._build_name_index({})
        assert index == {}


# =====================================================================
# _find_player with index
# =====================================================================

class TestFindPlayerWithIndex:
    def test_exact_match_via_index(self):
        _load_db({
            "100": _make_player("100", "Patrick Mahomes", team="KC"),
        })
        result = player_news._find_player("Patrick Mahomes")
        assert result is not None
        assert result["player_id"] == "100"

    def test_case_insensitive_match(self):
        _load_db({
            "100": _make_player("100", "Patrick Mahomes", team="KC"),
        })
        result = player_news._find_player("patrick mahomes")
        assert result is not None
        assert result["player_id"] == "100"

    def test_whitespace_stripped(self):
        _load_db({
            "100": _make_player("100", "Patrick Mahomes", team="KC"),
        })
        result = player_news._find_player("  Patrick Mahomes  ")
        assert result is not None
        assert result["player_id"] == "100"

    def test_no_match_returns_none(self):
        _load_db({
            "100": _make_player("100", "Patrick Mahomes", team="KC"),
        })
        result = player_news._find_player("Nonexistent Player")
        assert result is None

    def test_duplicate_name_resolution(self):
        _load_db({
            "300": _make_player("300", "Mike Williams", active=False, team=None),
            "301": _make_player("301", "Mike Williams", active=True, team="NYJ"),
        })
        result = player_news._find_player("Mike Williams")
        assert result is not None
        assert result["player_id"] == "301"

    def test_fallback_to_linear_scan_when_index_empty(self):
        """If the index is empty but DB has entries, fallback should find them."""
        player_news._player_db = {
            "100": _make_player("100", "Patrick Mahomes", team="KC"),
        }
        player_news._name_index = {}  # Simulate empty index
        result = player_news._find_player("Patrick Mahomes")
        assert result is not None
        assert result["player_id"] == "100"
