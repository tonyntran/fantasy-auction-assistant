# Phase 3 — UX Polish: Change Summary

All 5 tickets implemented. Tests passing (221), dashboard builds clean.

---

## CHORE-003: Decompose `_get_dashboard_snapshot`

**File:** `backend/server.py`

**Changes:** The 280-line monolith decomposed into 11 focused helper functions + thin orchestrator:

| Function | Purpose |
|----------|---------|
| `_build_player_list()` | All players with FMV, VORP, VONA, tier, draft status |
| `_build_top_remaining()` | Top 5 undrafted per position with tier-break flags |
| `_build_ticker_events()` | Recent ticker events with team aliases |
| `_build_current_advice()` | Advice dict for active nomination (engine + cached AI) |
| `_build_opponent_needs()` | Opponent positional needs with aliases |
| `_build_vom_leaderboard()` | Value Over Market leaderboard |
| `_build_positional_prices()` | Actual price vs FMV percentage per position |
| `_build_positional_run()` | Detect 3+ consecutive same-position sales |
| `_build_money_velocity()` | League-wide spending velocity metrics |
| `_build_my_team_data()` | My team data augmented with NFL team/bye info |
| `_build_budgets()` | Team budgets with aliases |

Return value identical — all 28 dict keys preserved, zero logic changes.

---

## FEAT-001: Persist dashboard preferences in localStorage

**Files created:** `dashboard/src/hooks/usePersistedState.js`

**Files modified:** `dashboard/src/App.jsx`, `dashboard/src/components/DraftBoard.jsx`

**Changes:**
- Generic `usePersistedState` hook wrapping `useState` + `localStorage` under single `faa_prefs` key
- Strategy selection persists and auto-restores on reload (syncs with backend via POST)
- DraftBoard position filter persists across reloads
- Search terms and sort state intentionally NOT persisted

---

## FEAT-003: Sortable DraftBoard columns

**File:** `dashboard/src/components/DraftBoard.jsx`

**Changes:**
- Click any column header to sort (Name, Position, Tier, FMV, VORP, VONA, Price)
- Click same column again to toggle asc/desc
- Sort indicator arrows (▲/▼) on active column
- Drafted players always sort to bottom regardless of sort key
- Default sort (no column selected) preserves original VORP descending behavior
- Sort state resets on data refresh (not persisted)
- Headers styled with `cursor-pointer`, `hover:text-primary`, `select-none`

---

## FEAT-005: Manual input panel in dashboard

**Files created:** `dashboard/src/components/ManualInput.jsx`

**Files modified:** `dashboard/src/App.jsx`

**Changes:**
- Collapsible command panel at top of dashboard (collapsed by default)
- Text input POSTs to `/manual` endpoint
- Supports: `sold`, `undo`, `budget`, `nom`, `suggest`
- Command history shows last 5 results (green=success, red=error)
- Enter key support, auto-clear on success, auto-focus after command
- Loading spinner during request
- Collapsible command reference listing all supported commands
- Dashboard auto-refreshes via `refetch` callback after successful commands
- Wrapped in ErrorBoundary

---

## FEAT-002: Extension options page

**Files created:** `extension/options.html`, `extension/options.js`

**Files modified:** `extension/manifest.json`, `extension/background.js`, `extension/content-bridge.js`, `extension/content.js`, `extension/style.css`

**Changes:**
- Options page with dark theme: configurable Server URL and Overlay Position (4 corners)
- Settings stored in `chrome.storage.sync` (syncs across devices)
- `background.js`: Replaced 3 hardcoded URL constants with async `getServerUrl()` reading from storage
- `content-bridge.js`: Relays overlay position from storage to MAIN world content script
- `content.js`: `applyOverlayPosition()` function sets CSS for any corner; drag handler updated for bottom-positioned overlays
- Real-time updates via `chrome.storage.onChanged` — no browser restart needed
- Team name kept as backend-only (not in extension options)

### Defaults
- Server URL: `http://localhost:8000`
- Overlay Position: `top-right`
