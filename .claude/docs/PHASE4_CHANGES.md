# Phase 4 — Features: Change Summary

All 4 tickets implemented. Tests passing (221), dashboard builds clean.

---

## FEAT-004: What-if simulator modal in dashboard

**Files created:** `dashboard/src/components/WhatIfModal.jsx`

**Files modified:** `dashboard/src/components/DraftBoard.jsx`

**Changes:**
- Clicking an undrafted player's name opens a what-if simulation modal
- Player names styled as clickable: `cursor-pointer hover:text-primary hover:underline` (undrafted only)
- Modal shows player name (read-only) + price input (defaults to rounded FMV)
- "Simulate" calls `GET /whatif?player=...&price=...`
- Results display: remaining budget, roster completeness badge, projected total points (color-coded), optimal remaining picks table
- Close via X button or backdrop click
- Error responses shown inline in modal
- Wrapped in ErrorBoundary
- Purely informational — no real state mutation

---

## FEAT-006: Draft grade display in dashboard

**Files created:** `dashboard/src/components/DraftGrade.jsx`

**Files modified:** `dashboard/src/App.jsx`

**Changes:**
- "Grade My Draft" button appears when roster is 80%+ filled
- On-demand only — never calls `/grade` automatically
- Handles all 3 backend response shapes:
  - Full AI grade: overall grade, strengths, weaknesses, best/worst picks, waiver targets, position grades
  - Engine-only fallback: statistical summary with total spent, projected points, surplus
  - Raw text fallback: pre-wrap display of unparsed AI response
- Color-coded grades: A=green, B=blue, C=yellow, D/F=red
- 30-second timeout with AbortController
- Loading spinner: "AI is grading your draft..."
- Dismissible with re-grade option
- Placed in right sidebar below RosterOptimizer

---

## FEAT-008: Player comparison tool

**Files created:** `dashboard/src/components/PlayerComparison.jsx`

**Files modified:** `dashboard/src/components/DraftBoard.jsx`

**Changes:**
- "Compare" toggle button next to Draft Board title
- When active, checkbox column appears (first column, undrafted only)
- Max 3 players selectable — remaining checkboxes disabled at limit
- Selected rows highlighted with subtle `bg-primary/10`
- Floating compare bar at bottom when 2+ selected (count, Compare button, Clear)
- Comparison modal shows side-by-side metrics table:
  - Tier (lowest = best), Projected Pts (highest = best), FMV (display only), VORP (highest = best), VONA (highest = best), AAV (display only)
  - Winner per metric: `font-bold text-success`
  - Equal values: no highlight
- Toggle off clears all selections and closes modal
- No backend calls — all data already available in player objects

---

## CHORE-009: Add `_reset_for_testing()` to singletons

**Files modified:** `backend/state.py`, `backend/ticker.py`, `backend/event_store.py`, `backend/tests/conftest.py`

**Changes:**
- Added `_reset_for_testing()` classmethod to `DraftState`, `TickerBuffer`, `EventStore`
- `EventStore` version also closes open file handle before reset (prevents resource leaks)
- `conftest.py` fixture updated to call `_reset_for_testing()` instead of directly setting `_instance = None`
- Underscore prefix signals test-only usage
- Singleton pattern itself unchanged — just formalized the reset mechanism
