# Phase 5 — Growth: Change Summary

All 3 tickets implemented. Tests passing (221), dashboard builds clean.

Deferred to future epics: Mock Simulator (FEAT-009), Mobile Responsive (FEAT-012), Historical Prices (FEAT-014).

---

## FEAT-010: Keeper/dynasty league support

**Files created:** `backend/keepers.py`

**Files modified:** `backend/config.py`, `backend/models.py`, `backend/state.py`, `backend/server.py`, `backend/.env.example`, `dashboard/src/components/DraftBoard.jsx`, `dashboard/src/components/MyRoster.jsx`

**Changes:**
- `KEEPERS_CSV` env var for CSV path (format: `PlayerName,Team,Price`)
- `keepers.py` module: loads CSV, marks players as drafted with `is_keeper=True`, updates team budgets, fills roster slots (dedicated > flex > bench priority)
- `is_keeper: bool = False` field added to `PlayerState` model
- Keepers loaded in startup sequence: after projections, before event replay
- Budget math: keeper costs reduce team budgets, flowing through to inflation calculations
- "K" badge displayed on keeper players in DraftBoard and MyRoster
- `is_keeper` included in dashboard snapshot player data
- Case-insensitive team matching via `state._is_my_team()`
- Edge cases handled: missing CSV, player not found, duplicates, invalid prices
- Non-keeper flow completely unchanged when `KEEPERS_CSV` is empty

---

## FEAT-011: Multi-sheet projection selector

**Files modified:** `backend/config.py`, `backend/state.py`, `backend/server.py`, `dashboard/src/components/Header.jsx`, `dashboard/src/App.jsx`

**Changes:**
- `available_sheets` property on Settings — builds `{label: path}` dict from `csv_path` + `csv_paths`
- `active_sheet` attribute on DraftState — tracks currently loaded sheet
- `reload_projections(csv_path)` method — reloads projections while preserving draft progress (drafted status, prices, team assignments, rosters, budgets)
- `POST /projection-sheet` endpoint — validates sheet name, reloads, broadcasts updated snapshot via WebSocket
- `available_sheets` and `active_sheet` included in dashboard snapshot
- Header dropdown selector — only visible when 2+ sheets configured
- `setSheet` handler in App.jsx — POSTs to endpoint, triggers refetch
- Single-sheet flow untouched — dropdown hidden when only one sheet

**Usage:** Set `CSV_PATHS=data/fantasypros.csv,data/espn.csv` in .env alongside `CSV_PATH=data/sheet_2026.csv`. All three sheets appear in the dropdown. Switching re-computes VORP/FMV/VONA from the new source while keeping all draft progress intact.

---

## FEAT-013: Export draft results

**Files created:** `dashboard/src/components/ExportButton.jsx`

**Files modified:** `backend/server.py`, `dashboard/src/App.jsx`

**Changes:**
- `GET /export?format=json|csv` endpoint:
  - Iterates all drafted players, computes FMV, VORP, VOM, projected points
  - Sorts by price descending
  - Returns full export with metadata, all picks, my picks, and summary stats
  - CSV format returns `StreamingResponse` with proper Content-Disposition header
  - JSON format auto-saves to `data/historical/draft_{date}_{platform}.json`
- `_auto_save_historical()` helper — creates `data/historical/` directory, saves JSON
- ExportButton component — appears at 60%+ roster completion
- Two buttons: "Export JSON" and "Export CSV"
- Browser download via temporary anchor element + Blob URL
- Placed in right sidebar below DraftGrade, wrapped in ErrorBoundary
