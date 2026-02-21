# Phase 1 — Quick Wins: Change Summary

All 7 tickets implemented. Review each section below.

---

## BUG-001: Fix slot name parsing in AI context builder

**File:** `backend/ai_advisor.py` (lines 100, 111)

**Problem:** `slot.split()[0]` on slot names like `"RB1"`, `"FLEX2"` returned the entire string (no spaces to split on), feeding garbled position labels into the AI context.

**Fix:** Replaced with `my.slot_types.get(slot, slot.rstrip("0123456789"))` — the same pattern used in `state.py`, `engine.py`, `what_if.py`, and `models.py`.

---

## CHORE-004: Create .env.example

**File:** `backend/.env.example` (new file)

**What:** Created a documented environment configuration template covering all variables from `config.py`, grouped logically: Core Settings, AI Configuration, Sleeper/ESPN, Draft Settings, Data Paths, VORP Baselines (football + basketball).

**Note:** Defaults reflect the corrected values (claude/sleeper).

---

## CHORE-005: Fix config.py defaults to claude/sleeper

**Files:** `backend/config.py`, `OVERVIEW.md`

**Changes:**
- `config.py` line 114: `platform: str = "espn"` → `platform: str = "sleeper"`
- `config.py` line 120: `ai_provider: str = "gemini"` → `ai_provider: str = "claude"`
- `OVERVIEW.md` configuration table: Updated defaults for `AI_PROVIDER` and `PLATFORM` to match

**Note:** ESPN and Gemini remain fully supported when specified via env var.

---

## BUG-003: Fix hardcoded AI provider labels in logs

**File:** `backend/ai_advisor.py`

**Problem:** All print/log statements hardcoded `"Gemini"` regardless of which provider was configured.

**Fix:** Added module-level `_provider_label = settings.ai_provider.capitalize()` and replaced all 6 hardcoded "Gemini" references in print statements with f-string `{_provider_label}`. Updated docstrings to say "AI provider" instead of "Gemini". Left Gemini-specific function names (`_call_gemini`) unchanged since they describe the actual API functions.

---

## BUG-008: Remove unused sse-starlette dependency

**File:** `backend/requirements.txt`

**Change:** Removed `sse-starlette` — confirmed via grep that it's not imported anywhere in the codebase.

---

## BUG-005: Fix EventStore sequence counter

**File:** `backend/event_store.py` (lines 39-48)

**Problem:** `open()` counted all non-empty lines for sequence numbering, including malformed/corrupted lines. This inflated the sequence counter.

**Fix:** Added `json.loads()` validation before incrementing `self._seq`. Malformed lines are silently skipped. This matches the defensive pattern already used in `replay()` (lines 66-72). No new imports needed (`json` was already imported).

---

## CHORE-002: Consolidate duplicate name normalization

**Files:** `backend/adp.py`, `backend/projections.py`, `backend/state.py`, `backend/fuzzy_match.py`

**Problem:** Three separate `_normalize()` implementations duplicating the canonical `normalize_name()` from `fuzzy_match.py`.

**Changes:**
- `adp.py`: Removed local `_normalize()` + `import re`, added `from fuzzy_match import normalize_name`, updated call site
- `projections.py`: Same as above
- `state.py`: `_normalize_name()` method now delegates to imported `normalize_name()` (kept as thin wrapper to avoid changing all internal call sites)
- `fuzzy_match.py`: Updated comments referencing `state._normalize_name()`, simplified `resolve_or_original()` to use `normalize_name()` directly

**Behavioral note:** `state.py`'s old normalization was simpler (just `lower().strip().rstrip(".")`). It now uses the more aggressive normalization that also strips suffixes (Jr/Sr/II/III) and punctuation. This is correct since it aligns with how `NameResolver`, `adp.py`, and `projections.py` already normalized names.

**No circular dependencies:** `fuzzy_match.py` does not import from `state`, `adp`, or `projections`.
