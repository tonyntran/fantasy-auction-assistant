# Phase 2 — Resilience: Change Summary

All 6 tickets implemented. 221 tests passing.

---

## CHORE-001: Add comprehensive test suite (XL)

**Files created:**
- `backend/pyproject.toml` — pytest configuration
- `backend/tests/__init__.py` — package marker
- `backend/tests/conftest.py` — shared fixtures (singleton reset, sample CSV data, draft state factory, mock payloads)
- `backend/tests/test_engine.py` — VORP, FMV, VONA, scarcity, need, strategy multipliers, advice generation (39 tests)
- `backend/tests/test_state.py` — CSV loading, draft events, player lookup, roster slots, aggregates (30 tests)
- `backend/tests/test_models.py` — Pydantic model validation, MyTeam slot management (26 tests)
- `backend/tests/test_config.py` — Settings defaults, roster parsing, sport profiles, strategies (25 tests)
- `backend/tests/test_event_store.py` — Append, replay, sequence counting, malformed line handling (16 tests)
- `backend/tests/test_nomination.py` — Draft phases, strategies, opponent targeting (12 tests)
- `backend/tests/test_what_if.py` — State cloning, simulation, greedy fill (14 tests)
- `backend/tests/test_player_news.py` — Name index build, duplicate resolution, lookup (13 tests)

**Files modified:** `backend/requirements.txt` (added pytest, pytest-asyncio, pytest-cov)

**Coverage highlights:**
- `models.py`: 100%
- `config.py`: 97%
- `event_store.py`: 97%
- `what_if.py`: 90%
- `state.py`: 87%
- `nomination.py`: 83%
- `engine.py`: 79%

**Result:** 221 tests, all passing in ~2s.

---

## CHORE-006: Add React error boundaries

**Files created:** `dashboard/src/components/ErrorBoundary.jsx`

**Files modified:** `dashboard/src/App.jsx`

**Changes:** All 11 major dashboard components wrapped with `<ErrorBoundary name="...">`. Individual component crashes now show a friendly error card with retry button instead of taking down the entire dashboard. Header intentionally not wrapped.

---

## BUG-002: Fix hardcoded 2025 bye week data

**File:** `backend/player_news.py`

**Changes:** Removed the entire hardcoded `_NFL_BYE_WEEKS` dictionary (2025 season data). Bye weeks now sourced from Sleeper player metadata (`metadata.bye_week`). When unavailable, bye week is simply omitted. Downstream code (server.py, MyRoster.jsx) already handles null safely.

---

## BUG-006: Simplify WebSocket `/ws` handler to read-only

**File:** `backend/server.py`

**Changes:** Removed state mutation logic from the WS handler. It now accepts connections, adds to client set, keeps alive (discards incoming messages), and removes on disconnect. State changes only happen via HTTP `POST /draft_update`, which broadcasts properly. Docstring updated to document subscription-only behavior.

---

## CHORE-010: Reuse httpx.AsyncClient across AI calls

**Files:** `backend/ai_advisor.py`, `backend/draft_plan.py`, `backend/server.py`

**Changes:**
- Added `get_http_client()` / `close_http_client()` in `ai_advisor.py` with lazy initialization
- Replaced 5 `async with httpx.AsyncClient()` blocks (3 in ai_advisor, 2 in draft_plan) with shared client
- `draft_plan.py` imports from `ai_advisor` — single shared connection pool
- Per-request timeouts (5s/10s/15s) since different calls need different limits
- Clean shutdown added to FastAPI lifespan in `server.py`

---

## CHORE-011: Build name-indexed Sleeper player lookup

**File:** `backend/player_news.py`

**Changes:** Added `_build_name_index()` that creates `{full_name.lower(): player_info}` dict on DB load. `_find_player()` now does O(1) dict lookup with linear scan fallback. Duplicate names resolved by preferring active players with team assignments. Index built once per 30-minute DB refresh. Includes 13 unit tests.

**Performance:** 140 x 9000 linear comparisons → 140 dict lookups per dashboard refresh.
