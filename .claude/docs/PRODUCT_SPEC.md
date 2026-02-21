# Fantasy Auction Assistant -- Product Specification

**Date:** 2026-02-20
**Version:** 1.0
**Status:** Draft

---

## 1. Executive Summary

Fantasy Auction Assistant is a real-time auction draft assistant supporting Sleeper and ESPN platforms. It combines a Chrome extension (WebSocket interception + React Fiber scraping), a Python FastAPI backend (VORP/FMV/scarcity engine + Claude/Gemini AI), and a React dashboard (12 components, real-time WebSocket updates).

This document is a comprehensive product audit covering code health, competitive landscape, and a prioritized roadmap of bugs, chores, features, and epics. Each ticket is self-contained and implementation-ready for AI code generation agents.

### Key Findings

- **19 bugs and code quality issues** identified across backend, extension, and dashboard
- **Zero test coverage** -- the single highest-risk technical debt item
- **Duplicate code** in 3+ files for name normalization
- **Documentation inconsistencies** between README, OVERVIEW, and actual defaults
- **Strong feature set** that already exceeds most free competitors; biggest gaps are mobile/tablet support, multi-league management, and historical analytics

---

## 2. Code Health Audit

### 2.1 Bugs and Potential Bugs

#### BUG-001: `_build_context` slot name parsing produces wrong base position types
- **File:** `backend/ai_advisor.py`, lines 98-106
- **Severity:** Medium
- **Description:** The `other_needs` section splits slot names on space (`base = slot.split()[0]`) but roster slot names like `RB1`, `FLEX2`, `QB` do not contain spaces. `"RB1".split()[0]` returns `"RB1"`, not `"RB"`. This means `state.get_remaining_players("RB1")` returns empty lists because there is no position called "RB1", so the AI context about alternative positions at unfilled slots is always empty.
- **Fix:** Replace `slot.split()[0]` with `state.my_team.slot_types.get(slot, slot.rstrip("0123456789"))` to get the base position type (e.g., "RB" from "RB1", "FLEX" from "FLEX2"). Then map FLEX/SUPERFLEX/BENCH to their eligible positions using `settings.SLOT_ELIGIBILITY`.
- **Also at:** Line 111 (`filled_positions` section) has the same `slot.split()[0]` pattern.

#### BUG-002: Hardcoded 2025 bye weeks with 2026 projection data
- **File:** `backend/player_news.py`, lines 196-205
- **Severity:** Medium
- **Description:** `_NFL_BYE_WEEKS` is hardcoded for the 2025 NFL season. The projection data in `data/sheet_2026.csv` is for the 2026 season. Bye weeks change every year, so roster display shows wrong bye weeks for every team.
- **Fix:** Either (a) fetch bye weeks dynamically from Sleeper's schedule API, or (b) make `_NFL_BYE_WEEKS` a configuration file loaded at startup, or (c) add a `BYE_WEEKS_SEASON` env var and a schedule lookup.

#### BUG-003: `ai_advisor.py` print statements reference "Gemini" even when using Claude
- **File:** `backend/ai_advisor.py`, lines 265, 270, 286, 290, 293, 296
- **Severity:** Low (cosmetic, but confusing when debugging)
- **Description:** All `print()` statements say `[AI] Gemini` regardless of which provider is configured. The module docstring (line 1-8) also says "Gemini" throughout.
- **Fix:** Replace all hardcoded "Gemini" references with `settings.ai_provider` or a generic "AI" label. Update docstring to be provider-neutral.

#### BUG-004: `stream/{player}` endpoint name is misleading
- **File:** `backend/server.py`, lines 568-574
- **Severity:** Low
- **Description:** The endpoint `/stream/{player}` suggests Server-Sent Events or streaming, but it returns a regular JSON response. The root endpoint (line 647) also labels it "SSE streaming AI advice". This is confusing for API consumers and documentation.
- **Fix:** Rename to `/advice/{player}` or keep `/stream/{player}` but add a deprecation warning. Update the root endpoint description.

#### BUG-005: EventStore sequence counter increments on malformed lines
- **File:** `backend/event_store.py`, lines 39-43
- **Severity:** Low
- **Description:** In `EventStore.open()`, the sequence counter counts all non-empty lines including malformed ones. If a line is corrupted JSON, `_seq` still increments. Meanwhile, `replay()` skips malformed lines via `try/except`. This means `_seq` could be higher than the actual number of valid events.
- **Fix:** Parse JSON in `open()` to count only valid events, or count only lines that `json.loads()` succeeds on.

#### BUG-006: WebSocket `/ws` endpoint partially implemented
- **File:** `backend/server.py`, lines 655-669
- **Severity:** Medium
- **Description:** The `/ws` endpoint processes incoming `DraftUpdate` messages but never sends back advice or broadcasts snapshots in response to those messages. It only broadcasts when the HTTP `/draft_update` endpoint is called. If a client sends data via WebSocket, it updates state silently without broadcasting. The extension uses HTTP POST, so this is not broken in the current flow, but the WebSocket handler creates an inconsistent code path.
- **Fix:** Either (a) add broadcast logic to the WS handler matching `/draft_update`, or (b) simplify the WS handler to be read-only (remove the state update logic).

#### BUG-007: `_replay_manual_command` sold regex is too greedy
- **File:** `backend/server.py`, lines 152-163
- **Severity:** Medium
- **Description:** The sold regex `^(.+?)\s+(\d+)(?:\s+(\d+))?\s*$` will match any command that ends with a number, including partial matches. For example, "nom Patrick Mahomes 30" would not match `nom_match` first during replay because `_replay_manual_command` does not check for `nom` prefix -- it falls through to `sold_match`. However, line 91-92 skips "nom" commands during replay, so this is partially mitigated but fragile.
- **Fix:** Add `sold` prefix requirement to the sold regex, or restructure command parsing to use an explicit keyword-first approach.

#### BUG-008: `sse-starlette` in requirements.txt but never imported
- **File:** `backend/requirements.txt`, line 7
- **Severity:** Low (wasted dependency)
- **Description:** `sse-starlette` is listed as a dependency but is never imported anywhere in the codebase. The `/stream/{player}` endpoint returns regular JSON, not SSE.
- **Fix:** Remove `sse-starlette` from `requirements.txt`.

### 2.2 Performance Issues

#### PERF-001: `_get_dashboard_snapshot` is a 280-line mega-function
- **File:** `backend/server.py`, lines 710-987
- **Severity:** Medium
- **Description:** This function computes ~15 different data structures on every call: player list, top remaining, ticker events, current advice, opponent needs, player news, VOM leaderboard, optimizer, position prices, positional runs, money velocity, and more. It is called on every `/draft_update` (for WebSocket broadcast) AND every `GET /dashboard/state` (initial load).
- **Impact:** During an active draft with 140 players and 10 teams, this function recalculates everything from scratch each time. The optimizer alone does a greedy O(players x roster_size) search.
- **Fix:** Break into smaller functions: `_build_player_list()`, `_build_top_remaining()`, `_build_current_advice()`, `_build_vom_leaderboard()`, `_build_market_analytics()`, etc. Consider caching intermediate results that don't change between ticks (e.g., position prices only change when a player is sold, not on bid updates).

#### PERF-002: VONA recomputed for ALL undrafted players on every state update
- **File:** `backend/state.py`, lines 243-251; `backend/engine.py`, lines 17-36
- **Severity:** Medium
- **Description:** `_compute_vonas()` is called from `_recompute_aggregates()` on every `update_from_draft_event()`. It iterates all undrafted players and for each one calls `calculate_vona()` which iterates the sorted remaining players at that position. With ~140 players across 6 positions, this is O(n^2) per position per update.
- **Fix:** Only recompute VONA for affected positions when a player is drafted (not all positions). Cache the sorted remaining lists.

#### PERF-003: New `httpx.AsyncClient` created per AI request
- **File:** `backend/ai_advisor.py`, lines 378-381, 404-405; `backend/draft_plan.py`, lines 293-295, 321-322
- **Severity:** Low
- **Description:** Each AI call creates a new `httpx.AsyncClient` instance inside an `async with` block. This means a new TCP connection pool is created and destroyed per request. For rapid sequential calls, this adds latency.
- **Fix:** Create a module-level `httpx.AsyncClient()` instance and reuse it across calls. Close it in the lifespan shutdown.

#### PERF-004: Sleeper player database loaded into memory (~40MB)
- **File:** `backend/player_news.py`, lines 22-28
- **Severity:** Low
- **Description:** The entire Sleeper player database (~9000+ entries) is fetched and held in memory as a Python dict. The `_find_player()` function does a linear scan over all entries for every lookup. With ~140 undrafted players, `get_news_for_undrafted()` does 140 linear scans of 9000 entries each.
- **Fix:** Build a name-indexed lookup dict on load: `{full_name.lower(): player_info}`.

### 2.3 Code Quality Issues

#### QUAL-001: Duplicate `_normalize()` function across 3 files
- **Files:**
  - `backend/adp.py`, lines 14-20
  - `backend/projections.py`, lines 14-20
  - `backend/fuzzy_match.py`, lines 35-47 (as `normalize_name()`)
  - `backend/state.py`, lines 175-178 (as `_normalize_name()`, simpler version)
- **Severity:** Medium
- **Description:** Four separate implementations of name normalization exist with slightly different logic. `adp.py` and `projections.py` have identical implementations. `fuzzy_match.py` has the most thorough version. `state.py` has a minimal version (just lowercase + strip + rstrip period).
- **Fix:** Consolidate into a single `normalize_name()` in `fuzzy_match.py` and import everywhere. The DraftState version can call the same function.

#### QUAL-002: Singleton pattern blocks testability
- **Files:**
  - `backend/state.py` (`DraftState.__new__`)
  - `backend/ticker.py` (`TickerBuffer.__new__`)
  - `backend/event_store.py` (`EventStore.__new__`)
- **Severity:** Medium
- **Description:** Three singletons use `__new__` class-level instance caching. This makes it impossible to create isolated instances for unit testing without monkey-patching `_instance = None`. It also creates hidden global mutable state.
- **Fix:** Use dependency injection: pass state/ticker/store instances through function parameters or FastAPI dependencies. For backward compatibility, provide a module-level default instance.

#### QUAL-003: No `.env.example` file
- **File:** Missing at `backend/.env.example`
- **Severity:** Low
- **Description:** README instructs `cp .env.example .env` but the file doesn't exist. New contributors cannot know which env vars to set.
- **Fix:** Create `backend/.env.example` with all variables from `config.py` and their defaults, with comments.

#### QUAL-004: README vs OVERVIEW configuration inconsistency
- **Files:** `README.md` line 60, `OVERVIEW.md` line 408, `backend/config.py` line 119
- **Severity:** Low
- **Description:** README says `AI_PROVIDER` default is `"claude"`. OVERVIEW says `"gemini"`. Config code shows default is `"gemini"`. README says `PLATFORM` default is `"sleeper"`. OVERVIEW says `"espn"`. Config code shows `"espn"`.
- **Fix:** Update README to match actual defaults in `config.py`: `AI_PROVIDER="gemini"`, `PLATFORM="espn"`.

#### QUAL-005: HTML string construction in server.py for overlay responses
- **File:** `backend/server.py`, lines 676-695 (`_format_advice_html`), and throughout `manual_override` (inline HTML strings)
- **Severity:** Low
- **Description:** HTML is built with string concatenation and inline styles. This is fragile, hard to maintain, and mixes presentation with business logic.
- **Fix:** Return structured JSON from the backend and let the extension overlay format the display. The overlay already handles rendering.

#### QUAL-006: `calculate_vorp` function is a no-op wrapper
- **File:** `backend/engine.py`, lines 12-14
- **Severity:** Low
- **Description:** `calculate_vorp(player)` just returns `player.vorp`. The VORP is pre-computed in `state.py._compute_vorps()`. This wrapper function adds no value and is misleading since it suggests computation is happening.
- **Fix:** Remove the wrapper and access `player.vorp` directly where used, or rename to `get_vorp()` to clarify it's a read accessor.

### 2.4 Security Concerns

#### SEC-001: CORS `allow_origins=["*"]` with no authentication
- **File:** `backend/server.py`, lines 167-172
- **Severity:** Medium (for local-only tool; High if deployed)
- **Description:** Wide-open CORS with no API authentication. Any website open in the same browser can call the backend endpoints. This is acceptable for localhost development but dangerous if the server is ever exposed.
- **Fix:** Restrict to `["http://localhost:5173", "http://localhost:8000", "chrome-extension://*"]`. Add optional API key header for non-local deployments.

#### SEC-002: No rate limiting on any API endpoint
- **File:** `backend/server.py` (entire file)
- **Severity:** Low (local tool)
- **Description:** No rate limiting on `/draft_update`, `/manual`, `/advice`, etc. A malicious script could hammer the AI endpoints, consuming API key quota.
- **Fix:** Add `slowapi` or a simple in-memory rate limiter middleware.

#### SEC-003: Extension hardcoded server URL with no configuration
- **File:** `extension/background.js`, lines 4-6
- **Severity:** Low
- **Description:** `SERVER_URL`, `MANUAL_URL`, and `HEALTH_URL` are hardcoded to `http://localhost:8000`. Users cannot change this without editing the source.
- **Fix:** Add an extension options page with configurable server URL stored in `chrome.storage.sync`.

### 2.5 Missing Infrastructure

#### INFRA-001: Zero test coverage
- **Severity:** Critical
- **Description:** No test files, no test configuration, no CI/CD pipeline. No `pytest.ini`, no `pyproject.toml` with test config, no `tests/` directory.
- **Impact:** Every change is deployed without validation. Refactoring is extremely risky.

#### INFRA-002: No type checking configuration
- **Severity:** Medium
- **Description:** No `mypy.ini`, `pyproject.toml` type checking config, or `py.typed` markers. Many functions lack type hints in their signatures.

#### INFRA-003: No linting or formatting configuration
- **Severity:** Low
- **Description:** No `ruff.toml`, `.flake8`, `pyproject.toml` with ruff/black config, or `.prettierrc`.

---

## 3. Market Research and Competitive Analysis

### 3.1 Competitive Landscape

| Tool | Price | Platform | Key Features | Weaknesses |
|---|---|---|---|---|
| **FantasyPros Draft Wizard** | $19-40/season | Web (ESPN/Yahoo/Sleeper sync) | Expert consensus rankings, mock draft simulator, auction value calculator, draft grades, VBD | No real-time bid interception, no AI advice, manual data entry during live draft |
| **Draft Sharks Auction Dominator** | $30/season | Web | Position-adjusted auction values, dollar-cost projections, strategy profiles | No live draft integration, static pre-draft tool only |
| **4for4 Auction Calculator** | $20/season | Web | Custom league settings, multi-source projection blending, AAV calculator | Pre-draft tool only, no real-time engine |
| **Jay Zheng's Auction Calculator** | Free | Web | Interactive auction tracker with real-time budget tracking, positional scarcity | No AI, no platform integration, requires manual input |
| **ESPN/Yahoo/Sleeper Built-In** | Free | Built into platform | Basic projected value, auto-draft, rank-based suggestions | No inflation tracking, no VORP/VONA, no opponent modeling, no strategic advice |
| **ChatGPT/Claude Manual** | $20/mo API | Manual copy-paste | Flexible analysis, deep reasoning | No draft state awareness, massive latency, requires manual context building |

### 3.2 Feature Gap Analysis

#### Features We Have That Competitors Lack
1. **Real-time platform integration** -- WebSocket interception means zero manual input
2. **Live inflation tracking** -- dynamically adjusts all valuations as the draft progresses
3. **AI-powered contextual advice** -- Claude/Gemini with full draft context (rosters, opponents, budget, scarcity)
4. **Opponent modeling** -- bidding war detection, positional need tracking, spending power analysis
5. **Nomination strategy engine** -- unique feature not found in any competitor
6. **Event sourcing for crash recovery** -- can restart mid-draft without data loss
7. **What-if simulator** -- project roster outcomes of hypothetical purchases
8. **Price enforcement logic** -- bid up opponents even when you don't need the player

#### Features Competitors Have That We Lack
1. **Pre-draft mock auction simulator** -- practice auctions against AI teams
2. **Multi-league support** -- manage multiple leagues simultaneously
3. **Historical price database** -- actual auction results from previous seasons for calibration
4. **Mobile/tablet responsive design** -- dashboard is desktop-only
5. **Social/sharing features** -- export draft results, share grades
6. **Keeper/dynasty league support** -- keeper values, multi-year projections
7. **Customizable scoring settings** -- PPR, half-PPR, standard, custom scoring impact on values
8. **Trade calculator integration** -- post-draft trade value comparisons
9. **Waiver wire integration** -- post-draft roster management

#### Market Gaps (Opportunities)
1. **No tool combines real-time interception + AI** -- we are unique here
2. **No free tool offers inflation-adjusted live values** -- Jay Zheng's is closest but manual
3. **No tool offers nomination strategy** -- this is a genuine innovation
4. **AI draft plan with spending allocation** -- no competitor offers this

---

## 4. Product Roadmap

### 4.1 Bugs (P0-P1)

---

#### TICKET: BUG-001 -- Fix slot name parsing in AI context builder
- **Type:** Bug
- **Priority:** P1
- **Description:** In `backend/ai_advisor.py` `_build_context()`, slot names are split on space (`slot.split()[0]`) to get base position types for the "other needs" section. Since slot names like `RB1`, `FLEX2`, `QB` contain no spaces, this always returns the full slot name. As a result, `state.get_remaining_players("RB1")` returns empty, and the AI never gets alternative position information.
- **Acceptance Criteria:**
  - `_build_context()` correctly extracts base position types from slot names (e.g., `RB1` -> `RB`, `FLEX2` -> `FLEX`)
  - FLEX/SUPERFLEX slots are expanded to their eligible positions using `settings.SLOT_ELIGIBILITY`
  - AI prompt includes top remaining players for each unfilled position
  - Both `other_needs` (line 98-106) and `filled_positions` (line 111) use the same correct logic
- **Implementation:**
  ```python
  # Replace: base = slot.split()[0]
  # With:
  base = state.my_team.slot_types.get(slot, slot.rstrip("0123456789"))
  ```
  For FLEX slots, expand to eligible positions:
  ```python
  eligible = settings.SLOT_ELIGIBILITY.get(base, [base])
  for pos in eligible:
      if pos not in other_needs:
          remaining = state.get_remaining_players(pos)[:3]
          other_needs[pos] = [...]
  ```
- **Files to Modify:** `backend/ai_advisor.py`
- **Estimated Complexity:** S

---

#### TICKET: BUG-002 -- Fix 2025 bye week data for 2026 season
- **Type:** Bug
- **Priority:** P1
- **Description:** `backend/player_news.py` has `_NFL_BYE_WEEKS` hardcoded for the 2025 NFL season, but projection data targets 2026. Bye weeks displayed in the roster are wrong.
- **Acceptance Criteria:**
  - Bye weeks are sourced dynamically, not hardcoded
  - Preferably fetched from Sleeper's metadata (the `metadata.bye_week` field on the player object)
  - Fallback to a configurable data file if Sleeper data is unavailable
  - Current season bye weeks are always accurate
- **Implementation:**
  1. In `get_player_roster_info()`, prefer `info.get("metadata", {}).get("bye_week")` which Sleeper may populate
  2. Add `BYE_WEEK_SOURCE` env var: `"sleeper"` (dynamic) or `"static"` (file)
  3. If static, load from `data/bye_weeks_2026.json`
  4. Remove hardcoded `_NFL_BYE_WEEKS` dict
- **Files to Modify:** `backend/player_news.py`
- **New Files:** `backend/data/bye_weeks_2026.json` (if static fallback needed)
- **Estimated Complexity:** S

---

#### TICKET: BUG-003 -- Fix AI provider label in logs and docstrings
- **Type:** Bug
- **Priority:** P2
- **Description:** `backend/ai_advisor.py` hardcodes "Gemini" in all print statements and docstrings regardless of which provider is configured. When using Claude, logs say `[AI] Gemini advice for ...`.
- **Acceptance Criteria:**
  - All print statements use `settings.ai_provider` or a generic "AI" label
  - Docstrings are provider-neutral
  - Module docstring updated
- **Implementation:** Search and replace all instances of `"Gemini"` in print/docstrings with dynamic label:
  ```python
  provider_label = settings.ai_provider.capitalize()
  print(f"  [AI] {provider_label} advice for {player_name}: ...")
  ```
- **Files to Modify:** `backend/ai_advisor.py`
- **Estimated Complexity:** S

---

#### TICKET: BUG-004 -- Rename misleading `/stream/{player}` endpoint
- **Type:** Bug
- **Priority:** P2
- **Description:** The `/stream/{player}` endpoint returns regular JSON, not SSE/streaming. The root endpoint description also calls it "SSE streaming AI advice".
- **Acceptance Criteria:**
  - Endpoint renamed to `/advice/{player}` or similar
  - Old `/stream/{player}` still works (redirect or alias) for backward compatibility
  - Root endpoint description updated
  - OVERVIEW.md API table updated
- **Files to Modify:** `backend/server.py`, `OVERVIEW.md`
- **Estimated Complexity:** S

---

#### TICKET: BUG-005 -- Fix EventStore sequence counter for malformed lines
- **Type:** Bug
- **Priority:** P2
- **Description:** `EventStore.open()` counts all non-empty lines for sequence numbering, but `replay()` skips malformed JSON lines. This can cause sequence gaps.
- **Acceptance Criteria:**
  - `open()` only counts lines that are valid JSON
  - Sequence numbers are consistent between `open()` and `replay()`
- **Implementation:**
  ```python
  def open(self, path: str):
      self._path = Path(path)
      self._path.parent.mkdir(parents=True, exist_ok=True)
      if self._path.exists():
          with open(self._path, "r", encoding="utf-8") as f:
              for line in f:
                  if line.strip():
                      try:
                          json.loads(line)
                          self._seq += 1
                      except json.JSONDecodeError:
                          pass  # Skip malformed lines
      self._file = open(self._path, "a", encoding="utf-8")
  ```
- **Files to Modify:** `backend/event_store.py`
- **Estimated Complexity:** S

---

#### TICKET: BUG-006 -- Partially implemented WebSocket `/ws` handler
- **Type:** Bug
- **Priority:** P2
- **Description:** The `/ws` endpoint processes incoming `DraftUpdate` messages but does not broadcast state snapshots afterward. This creates an inconsistent code path where state can be mutated without notifying dashboard clients.
- **Acceptance Criteria:**
  - Option A: Remove state update logic from WS handler (make it read-only/subscription-only)
  - Option B: Add full processing pipeline (ticker events, event store, broadcast) matching `/draft_update`
  - Either way, the behavior is consistent and documented
- **Files to Modify:** `backend/server.py`
- **Estimated Complexity:** S

---

#### TICKET: BUG-007 -- Remove unused `sse-starlette` dependency
- **Type:** Bug
- **Priority:** P2
- **Description:** `sse-starlette` is in `requirements.txt` but never imported. No SSE endpoints exist.
- **Acceptance Criteria:**
  - `sse-starlette` removed from `requirements.txt`
  - No import errors after removal
- **Files to Modify:** `backend/requirements.txt`
- **Estimated Complexity:** S

---

### 4.2 Technical Debt / Chores

---

#### TICKET: CHORE-001 -- Add comprehensive test suite (backend)
- **Type:** Chore
- **Priority:** P0
- **Description:** The entire codebase has zero test coverage. This is the highest-risk technical debt item. Every change is deployed without validation, and refactoring is dangerous.
- **Acceptance Criteria:**
  - `pytest` and `pytest-asyncio` added to `requirements.txt`
  - `backend/tests/` directory created
  - Test configuration in `pyproject.toml`
  - Minimum tests covering:
    - `engine.py`: All calculation functions (VORP, FMV, scarcity, need, strategy multipliers, advice logic)
    - `state.py`: CSV loading, draft event processing, roster slot assignment, fuzzy matching
    - `models.py`: Pydantic model validation and serialization
    - `config.py`: Setting parsing, roster slot parsing, sport profile resolution
    - `server.py`: Key endpoint responses (mock state)
    - `nomination.py`: Strategy selection logic
    - `what_if.py`: State cloning and simulation
    - `event_store.py`: Append, replay, sequence counting
  - At least 80% line coverage on `engine.py` and `state.py`
- **Implementation:**
  1. Create `backend/pyproject.toml` with pytest config
  2. Add `pytest`, `pytest-asyncio`, `pytest-cov` to `requirements.txt`
  3. Create `backend/tests/__init__.py`
  4. Create `backend/tests/conftest.py` with fixtures: sample CSV data, DraftState factory (bypassing singleton), mock DraftUpdate payloads
  5. Write test files: `test_engine.py`, `test_state.py`, `test_models.py`, `test_config.py`, `test_nomination.py`, `test_what_if.py`, `test_event_store.py`
- **Files to Create:** `backend/pyproject.toml`, `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/tests/test_engine.py`, `backend/tests/test_state.py`, `backend/tests/test_models.py`, `backend/tests/test_config.py`, `backend/tests/test_nomination.py`, `backend/tests/test_what_if.py`, `backend/tests/test_event_store.py`
- **Files to Modify:** `backend/requirements.txt`
- **Estimated Complexity:** XL

---

#### TICKET: CHORE-002 -- Consolidate duplicate name normalization
- **Type:** Chore
- **Priority:** P1
- **Description:** Name normalization is duplicated across 4 files with slightly different implementations. This violates DRY and can cause cross-source matching inconsistencies.
- **Acceptance Criteria:**
  - Single `normalize_name()` function in `backend/fuzzy_match.py` (the most thorough version)
  - `backend/adp.py`, `backend/projections.py`, `backend/state.py` all import from `fuzzy_match`
  - No duplicate normalization functions remain
  - All existing name matches still work (regression tested)
- **Implementation:**
  1. Keep `normalize_name()` in `fuzzy_match.py` as the canonical implementation
  2. In `adp.py`: Replace `_normalize()` with `from fuzzy_match import normalize_name`
  3. In `projections.py`: Replace `_normalize()` with `from fuzzy_match import normalize_name`
  4. In `state.py`: Replace `_normalize_name()` with import, or make it call `normalize_name()`
  5. Verify no behavioral changes in name matching
- **Files to Modify:** `backend/adp.py`, `backend/projections.py`, `backend/state.py`, `backend/fuzzy_match.py`
- **Estimated Complexity:** S

---

#### TICKET: CHORE-003 -- Decompose `_get_dashboard_snapshot` into smaller functions
- **Type:** Chore
- **Priority:** P1
- **Description:** `_get_dashboard_snapshot()` in `server.py` is ~280 lines computing 15+ data structures. This is hard to read, test, and maintain.
- **Acceptance Criteria:**
  - Function broken into 8+ smaller, named functions
  - Each sub-function is independently testable
  - No change in the snapshot output format
  - Functions created:
    - `_build_player_list(state)` -> list of player dicts
    - `_build_top_remaining(state)` -> dict of position -> top 5
    - `_build_current_advice(state)` -> advice dict or None
    - `_build_vom_leaderboard(state)` -> sorted VOM list
    - `_build_positional_prices(state)` -> position price tracking
    - `_build_positional_run(state)` -> run detection
    - `_build_money_velocity(state)` -> velocity metrics
    - `_build_my_team_data(state)` -> augmented team data
- **Files to Modify:** `backend/server.py`
- **Estimated Complexity:** M

---

#### TICKET: CHORE-004 -- Create `.env.example` file
- **Type:** Chore
- **Priority:** P1
- **Description:** README references `.env.example` but it doesn't exist. New contributors have no reference for configuration.
- **Acceptance Criteria:**
  - `backend/.env.example` created with all variables from `config.py`
  - Each variable has a comment explaining its purpose
  - Sensitive values (API keys) shown as placeholder text
  - README setup instructions work as documented
- **Files to Create:** `backend/.env.example`
- **Estimated Complexity:** S

---

#### TICKET: CHORE-005 -- Fix README/OVERVIEW configuration inconsistencies
- **Type:** Chore
- **Priority:** P1
- **Description:** README says `AI_PROVIDER` default is `"claude"` and `PLATFORM` default is `"sleeper"`. Actual defaults in `config.py` are `"gemini"` and `"espn"`.
- **Acceptance Criteria:**
  - README.md `Configuration` table matches `config.py` defaults exactly
  - OVERVIEW.md `Configuration` table matches `config.py` defaults exactly
  - No ambiguity about default values
- **Files to Modify:** `README.md`, `OVERVIEW.md`
- **Estimated Complexity:** S

---

#### TICKET: CHORE-006 -- Add React error boundaries to dashboard
- **Type:** Chore
- **Priority:** P1
- **Description:** Dashboard has no React error boundaries. If any component throws (e.g., due to unexpected null data from a backend change), the entire dashboard crashes.
- **Acceptance Criteria:**
  - `ErrorBoundary` wrapper component created
  - Each major component section wrapped with error boundary
  - Error state shows a friendly message with component name and "retry" button
  - Individual component failures don't crash the full dashboard
- **Implementation:**
  ```jsx
  // dashboard/src/components/ErrorBoundary.jsx
  import { Component } from 'react'
  class ErrorBoundary extends Component {
    state = { hasError: false, error: null }
    static getDerivedStateFromError(error) {
      return { hasError: true, error }
    }
    render() {
      if (this.state.hasError) {
        return (
          <div className="card bg-base-200 shadow-md">
            <div className="card-body p-4">
              <p className="text-xs text-error">Component error: {this.props.name}</p>
              <button className="btn btn-xs" onClick={() => this.setState({ hasError: false })}>Retry</button>
            </div>
          </div>
        )
      }
      return this.props.children
    }
  }
  ```
- **Files to Create:** `dashboard/src/components/ErrorBoundary.jsx`
- **Files to Modify:** `dashboard/src/App.jsx`
- **Estimated Complexity:** S

---

#### TICKET: CHORE-007 -- Add type checking with pyright/mypy
- **Type:** Chore
- **Priority:** P2
- **Description:** No type checking configuration exists. Many functions lack type annotations.
- **Acceptance Criteria:**
  - `pyproject.toml` configured with pyright or mypy settings
  - All function signatures in `engine.py`, `models.py`, `config.py` have complete type annotations
  - Zero type errors in strict mode for `engine.py` and `models.py`
  - Baseline established for other files
- **Files to Modify:** `backend/pyproject.toml`, `backend/engine.py`, `backend/models.py`
- **Estimated Complexity:** M

---

#### TICKET: CHORE-008 -- Add linting and formatting configuration
- **Type:** Chore
- **Priority:** P2
- **Description:** No linting or formatting tools configured. Inconsistent code style across files.
- **Acceptance Criteria:**
  - `ruff` configured in `pyproject.toml` for linting and formatting
  - `prettier` configured for JS/JSX files
  - All existing files pass lint checks (fix existing violations)
  - Pre-commit hook or CI check available
- **Files to Create:** `backend/pyproject.toml` (add ruff section), `dashboard/.prettierrc`
- **Estimated Complexity:** M

---

#### TICKET: CHORE-009 -- Refactor singletons into injectable dependencies
- **Type:** Chore
- **Priority:** P2
- **Description:** `DraftState`, `TickerBuffer`, and `EventStore` use the singleton pattern which blocks testability.
- **Acceptance Criteria:**
  - Each class can be instantiated independently (for testing)
  - A module-level convenience function or FastAPI dependency provides the default instance
  - Existing code continues to work without changes to call sites (backward compatible)
  - Tests can create fresh instances
- **Implementation:**
  1. Add `_reset_for_testing()` class method to each singleton
  2. Or: use FastAPI `Depends()` for state injection in endpoints
  3. Or: make singletons opt-in via a `get_instance()` classmethod while allowing normal `__init__` for tests
- **Files to Modify:** `backend/state.py`, `backend/ticker.py`, `backend/event_store.py`
- **Estimated Complexity:** M

---

#### TICKET: CHORE-010 -- Reuse httpx.AsyncClient across AI calls
- **Type:** Chore
- **Priority:** P2
- **Description:** Each AI API call creates and destroys an `httpx.AsyncClient`, wasting TCP connection setup time.
- **Acceptance Criteria:**
  - Module-level `httpx.AsyncClient` instance shared across calls
  - Client closed properly on application shutdown (lifespan)
  - No connection leak
- **Files to Modify:** `backend/ai_advisor.py`, `backend/draft_plan.py`, `backend/server.py` (lifespan cleanup)
- **Estimated Complexity:** S

---

#### TICKET: CHORE-011 -- Build name-indexed lookup for Sleeper player database
- **Type:** Chore
- **Priority:** P2
- **Description:** `player_news._find_player()` does a linear scan over 9000+ entries for every name lookup.
- **Acceptance Criteria:**
  - On load, build `_name_index: dict[str, dict]` mapping `full_name.lower()` -> player info
  - `_find_player()` uses O(1) dict lookup instead of O(n) scan
  - Handle duplicate names (prefer active players)
- **Files to Modify:** `backend/player_news.py`
- **Estimated Complexity:** S

---

### 4.3 Feature Enhancements (P1-P2)

---

#### TICKET: FEAT-001 -- Persist dashboard preferences in localStorage
- **Type:** Feature
- **Priority:** P1
- **Description:** Strategy selection, column filters, search terms, and collapsed panels all reset on page reload. Users must reconfigure the dashboard every time they refresh.
- **Acceptance Criteria:**
  - Active strategy selection persists across reloads
  - DraftBoard position filter persists
  - DraftBoard search term clears on reload (intentional -- stale searches are confusing)
  - Collapsed/expanded state of each panel persists
  - Preferences stored in `localStorage` under a `faa_prefs` key
- **Implementation:**
  1. Create `dashboard/src/hooks/usePersistedState.js` hook wrapping `useState` + `localStorage`
  2. Apply to strategy selector in `Header.jsx`
  3. Apply to position filter in `DraftBoard.jsx`
- **Files to Create:** `dashboard/src/hooks/usePersistedState.js`
- **Files to Modify:** `dashboard/src/App.jsx`, `dashboard/src/components/Header.jsx`, `dashboard/src/components/DraftBoard.jsx`
- **Estimated Complexity:** S

---

#### TICKET: FEAT-002 -- Add Chrome extension options page
- **Type:** Feature
- **Priority:** P1
- **Description:** The extension has no way to configure the server URL, team name, or other settings. Users must edit `background.js` source code.
- **Acceptance Criteria:**
  - `extension/options.html` and `extension/options.js` created
  - Configurable fields: Server URL, My Team Name, Overlay position (top-right/top-left/bottom-right/bottom-left)
  - Settings stored in `chrome.storage.sync`
  - `background.js` reads server URL from storage instead of hardcoded constant
  - `manifest.json` updated with `options_page`
- **Files to Create:** `extension/options.html`, `extension/options.js`
- **Files to Modify:** `extension/manifest.json`, `extension/background.js`
- **Estimated Complexity:** M

---

#### TICKET: FEAT-003 -- Add sortable columns to DraftBoard
- **Type:** Feature
- **Priority:** P1
- **Description:** The DraftBoard table sorts only by drafted status + VORP. Users cannot sort by FMV, VONA, price, tier, or projected points.
- **Acceptance Criteria:**
  - Clicking any column header sorts by that column (ascending/descending toggle)
  - Sort indicator (arrow) shown on active column
  - Default sort remains drafted-status + VORP descending
  - Columns sortable: Name, Position, Tier, FMV, VORP, VONA, Price
- **Files to Modify:** `dashboard/src/components/DraftBoard.jsx`
- **Estimated Complexity:** S

---

#### TICKET: FEAT-004 -- What-if simulator in the dashboard
- **Type:** Feature
- **Priority:** P2
- **Description:** The what-if simulator is only accessible via the extension overlay command input (`whatif PlayerName Price`). The dashboard should have a UI for it.
- **Acceptance Criteria:**
  - "What If" button/link on each undrafted player row in DraftBoard
  - Modal or side panel with player name (pre-filled) and price input
  - Submit calls `GET /whatif?player=...&price=...`
  - Results displayed: remaining budget, optimal remaining picks, projected total points
  - Can be dismissed without affecting state
- **Files to Create:** `dashboard/src/components/WhatIfModal.jsx`
- **Files to Modify:** `dashboard/src/components/DraftBoard.jsx` or `dashboard/src/App.jsx`
- **Estimated Complexity:** M

---

#### TICKET: FEAT-005 -- Add manual input panel to dashboard
- **Type:** Feature
- **Priority:** P2
- **Description:** The extension overlay supports manual commands (`sold`, `undo`, `budget`, `nom`, `suggest`), but the dashboard has no way to issue manual commands. This is critical when the extension scraper misses a pick.
- **Acceptance Criteria:**
  - Manual command input field at the top or bottom of the dashboard
  - Supports all commands: `sold PlayerName Price [TeamId]`, `undo PlayerName`, `budget N`, `nom PlayerName [Price]`
  - Response displayed inline (success/error)
  - State auto-refreshes after successful command
- **Files to Create:** `dashboard/src/components/ManualInput.jsx`
- **Files to Modify:** `dashboard/src/App.jsx`
- **Estimated Complexity:** S

---

#### TICKET: FEAT-006 -- Draft grade display in dashboard
- **Type:** Feature
- **Priority:** P2
- **Description:** Post-draft grading is accessible via `GET /grade` but has no dashboard UI. Users must use the browser or extension.
- **Acceptance Criteria:**
  - "Grade My Draft" button visible when draft is 80%+ complete
  - Shows overall grade, position grades, best/worst picks, waiver targets
  - Loading state while AI processes
  - Fallback to engine-only grade if AI unavailable
- **Files to Create:** `dashboard/src/components/DraftGrade.jsx`
- **Files to Modify:** `dashboard/src/App.jsx`
- **Estimated Complexity:** M

---

#### TICKET: FEAT-007 -- Inflation history chart in dashboard
- **Type:** Feature
- **Priority:** P2
- **Description:** The backend tracks `inflation_history` as a time series, but no component visualizes it. A chart would show how inflation changes over the draft.
- **Acceptance Criteria:**
  - Line chart (using recharts, already a dependency) showing inflation over time
  - X-axis: picks/time, Y-axis: inflation factor
  - Horizontal reference line at 1.0
  - Displayed in TeamOverview or as a standalone mini-component
- **Files to Modify:** `dashboard/src/components/TeamOverview.jsx`
- **Estimated Complexity:** S

---

#### TICKET: FEAT-008 -- Player comparison tool
- **Type:** Feature
- **Priority:** P2
- **Description:** During an auction, users often need to compare 2-3 players side-by-side. No comparison view exists.
- **Acceptance Criteria:**
  - Select 2-3 undrafted players from DraftBoard (checkbox or click-to-compare)
  - Side-by-side comparison panel showing: projected points, FMV, VORP, VONA, tier, scarcity multiplier
  - Visual indicators for which player is better on each metric
  - Dismiss button to clear comparison
- **Files to Create:** `dashboard/src/components/PlayerComparison.jsx`
- **Files to Modify:** `dashboard/src/components/DraftBoard.jsx`, `dashboard/src/App.jsx`
- **Estimated Complexity:** M

---

### 4.4 New Features (P2-P3)

---

#### TICKET: FEAT-009 -- Pre-draft mock auction simulator
- **Type:** Feature
- **Priority:** P2
- **Description:** No way to practice auction strategy before draft day. A mock auction simulator with AI-driven opponent bidding would let users test strategies.
- **Acceptance Criteria:**
  - `GET /mock/start` initializes a simulated draft with N AI teams
  - `POST /mock/nominate` triggers AI teams to bid
  - `POST /mock/bid` places user bid
  - AI teams bid based on their needs, budgets, and player values (simple rule-based)
  - Results tracked and gradeable
  - Dashboard mock mode
- **Files to Create:** `backend/mock_draft.py`, `dashboard/src/components/MockDraft.jsx`
- **Files to Modify:** `backend/server.py`
- **Estimated Complexity:** XL

---

#### TICKET: FEAT-010 -- Keeper/dynasty league support
- **Type:** Feature
- **Priority:** P3
- **Description:** No support for keeper leagues where some players are pre-assigned at specific prices. Keeper values reduce budgets and remove players from the pool.
- **Acceptance Criteria:**
  - `KEEPERS_CSV` env var pointing to a CSV of `PlayerName,Team,Price`
  - On load, keeper players are pre-drafted at their keeper price
  - Team budgets reduced by keeper costs
  - Engine calculations account for pre-filled roster slots
  - Dashboard shows keeper players with a "K" badge
- **Files to Create:** `backend/keepers.py`
- **Files to Modify:** `backend/server.py` (lifespan), `backend/state.py`, `backend/config.py`
- **Estimated Complexity:** M

---

#### TICKET: FEAT-011 -- Custom scoring settings impact on values
- **Type:** Feature
- **Priority:** P3
- **Description:** The engine uses raw projected points from CSV without accounting for scoring format (PPR, half-PPR, standard). Players' values should shift based on scoring rules.
- **Acceptance Criteria:**
  - `SCORING_FORMAT` env var: `"half_ppr"` (default), `"ppr"`, `"standard"`, `"custom"`
  - For custom, `SCORING_WEIGHTS` env var with JSON scoring rules
  - CSV loader applies scoring adjustments to projected points
  - VORP calculations reflect scoring-adjusted projections
- **Files to Modify:** `backend/config.py`, `backend/state.py`, `backend/projections.py`
- **Estimated Complexity:** M

---

#### TICKET: FEAT-012 -- Mobile-responsive dashboard layout
- **Type:** Feature
- **Priority:** P3
- **Description:** The dashboard is designed for desktop with a 4-column grid layout. On mobile/tablet, components stack awkwardly and some are too wide.
- **Acceptance Criteria:**
  - Dashboard renders usably on tablet (768px) and phone (375px)
  - Components reflow into single column on mobile
  - DraftBoard table scrolls horizontally
  - Touch-friendly button sizes
  - Key information (current advice, budget) visible without scrolling
- **Files to Modify:** `dashboard/src/App.jsx`, all component files (responsive class adjustments)
- **Estimated Complexity:** L

---

#### TICKET: FEAT-013 -- Export draft results
- **Type:** Feature
- **Priority:** P3
- **Description:** After the draft, there is no way to export results (roster, grades, VOM) for sharing or archival.
- **Acceptance Criteria:**
  - "Export" button in dashboard after draft completion
  - Exports to JSON and/or CSV
  - Includes: roster, prices, FMV at time of purchase, VOM, grade
  - Optional: shareable HTML report
- **Files to Create:** `dashboard/src/components/ExportButton.jsx`
- **Files to Modify:** `dashboard/src/App.jsx`
- **Estimated Complexity:** S

---

#### TICKET: FEAT-014 -- Historical auction price database
- **Type:** Feature
- **Priority:** P3
- **Description:** No historical data about actual auction prices from past seasons. This could calibrate FMV predictions and show "last year this player went for $X".
- **Acceptance Criteria:**
  - `data/historical_prices.csv` with `Season,PlayerName,Position,AuctionPrice,LeagueSize`
  - Historical reference shown in CurrentAdvice and DraftBoard
  - "Last year: $X" context for returning players
  - Automatically saved from completed drafts
- **Files to Create:** `backend/historical.py`, `backend/data/historical_prices.csv`
- **Files to Modify:** `backend/server.py`, `dashboard/src/components/CurrentAdvice.jsx`
- **Estimated Complexity:** M

---

### 4.5 Epics

---

#### EPIC-001: Testing and Quality Infrastructure
- **Description:** Establish comprehensive testing, type checking, linting, and CI/CD for the entire project.
- **Includes:**
  - CHORE-001 (test suite)
  - CHORE-007 (type checking)
  - CHORE-008 (linting/formatting)
  - New: CI pipeline (GitHub Actions) running tests, type checks, and lint on PR
  - New: Dashboard test setup (vitest + react-testing-library)
- **Estimated Complexity:** XL
- **Priority:** P0

---

#### EPIC-002: Code Health and Refactoring
- **Description:** Address all identified code quality issues, duplicate code, and architectural concerns.
- **Includes:**
  - CHORE-002 (consolidate normalization)
  - CHORE-003 (decompose mega-function)
  - CHORE-009 (refactor singletons)
  - CHORE-010 (reuse httpx client)
  - CHORE-011 (name-indexed lookup)
  - BUG-001 through BUG-007
- **Estimated Complexity:** L
- **Priority:** P1

---

#### EPIC-003: Dashboard UX Enhancement
- **Description:** Make the dashboard more interactive, resilient, and user-friendly.
- **Includes:**
  - CHORE-006 (error boundaries)
  - FEAT-001 (persisted preferences)
  - FEAT-003 (sortable columns)
  - FEAT-004 (what-if modal)
  - FEAT-005 (manual input panel)
  - FEAT-006 (draft grade display)
  - FEAT-007 (inflation chart)
  - FEAT-008 (player comparison)
- **Estimated Complexity:** XL
- **Priority:** P1

---

#### EPIC-004: Extension Polish
- **Description:** Improve the Chrome extension with configuration, better UX, and reliability.
- **Includes:**
  - FEAT-002 (options page)
  - SEC-003 (configurable server URL)
  - New: Extension popup showing connection status and quick stats
  - New: Overlay theming/customization options
  - New: Extension error recovery when Sleeper reconnects WebSocket
- **Estimated Complexity:** L
- **Priority:** P2

---

#### EPIC-005: Advanced Analytics and Simulation
- **Description:** Add pre-draft and post-draft analytical tools.
- **Includes:**
  - FEAT-009 (mock auction simulator)
  - FEAT-013 (export results)
  - FEAT-014 (historical price database)
  - New: Season projection model (weekly matchup-adjusted projections)
  - New: Trade value calculator for post-draft analysis
- **Estimated Complexity:** XL
- **Priority:** P3

---

#### EPIC-006: Multi-League and Keeper Support
- **Description:** Support advanced league formats and multi-league management.
- **Includes:**
  - FEAT-010 (keeper leagues)
  - FEAT-011 (custom scoring)
  - New: Multi-league instance management (switch between leagues)
  - New: Dynasty league multi-year projections
- **Estimated Complexity:** XL
- **Priority:** P3

---

## 5. Implementation Priority Matrix

### Effort vs Impact Grid

```
                           IMPACT
                    Low         Medium        High
              +------------+------------+------------+
         S    | BUG-004    | BUG-003    | BUG-001    |
  E      m    | BUG-005    | BUG-007    | CHORE-004  |
  F      a    | BUG-008    | CHORE-005  | CHORE-002  |
  F      l    |            | FEAT-001   | FEAT-003   |
  O      l    |            | CHORE-010  | FEAT-005   |
  R           |            | CHORE-011  |            |
  T      ----+------------+------------+------------+
         M    | CHORE-007  | FEAT-002   | CHORE-003  |
         e    | CHORE-008  | FEAT-004   | CHORE-006  |
         d    | FEAT-014   | FEAT-006   | BUG-006    |
         i    |            | FEAT-011   | FEAT-008   |
         u    |            |            | BUG-002    |
         m    |            |            |            |
              +------------+------------+------------+
         L    | FEAT-012   | FEAT-009   | CHORE-001  |
         a    | FEAT-013   | FEAT-010   | (tests)    |
         r    |            |            |            |
         g    |            |            |            |
         e    |            |            |            |
              +------------+------------+------------+
```

### Recommended Implementation Order

**Phase 1: Foundation (Weeks 1-2)**
1. CHORE-004 -- Create `.env.example` (S, 15 min)
2. CHORE-005 -- Fix README/OVERVIEW inconsistencies (S, 15 min)
3. BUG-001 -- Fix slot name parsing in AI context (S, 30 min)
4. BUG-003 -- Fix AI provider labels (S, 20 min)
5. BUG-008 -- Remove unused sse-starlette (S, 5 min)
6. BUG-005 -- Fix EventStore sequence counter (S, 15 min)
7. CHORE-002 -- Consolidate name normalization (S, 45 min)

**Phase 2: Resilience (Weeks 2-3)**
8. CHORE-001 -- Add test suite (XL, 2-3 days) -- **most critical**
9. CHORE-006 -- Add React error boundaries (S, 30 min)
10. BUG-002 -- Fix bye week data (S, 30 min)
11. BUG-006 -- Fix WebSocket handler (S, 20 min)
12. CHORE-010 -- Reuse httpx client (S, 30 min)
13. CHORE-011 -- Name-indexed player lookup (S, 20 min)

**Phase 3: UX Polish (Weeks 3-4)**
14. CHORE-003 -- Decompose `_get_dashboard_snapshot` (M, 2-3 hours)
15. FEAT-001 -- Persist dashboard preferences (S, 45 min)
16. FEAT-003 -- Sortable DraftBoard columns (S, 45 min)
17. FEAT-005 -- Manual input panel in dashboard (S, 1 hour)
18. FEAT-002 -- Extension options page (M, 2-3 hours)
19. FEAT-007 -- Inflation history chart (S, 1 hour)

**Phase 4: Features (Weeks 4-6)**
20. FEAT-004 -- What-if simulator in dashboard (M, 2-3 hours)
21. FEAT-006 -- Draft grade display (M, 2-3 hours)
22. FEAT-008 -- Player comparison tool (M, 2-3 hours)
23. CHORE-009 -- Refactor singletons (M, 2-3 hours)

**Phase 5: Growth (Weeks 6+)**
24. FEAT-010 -- Keeper league support (M)
25. FEAT-011 -- Custom scoring (M)
26. FEAT-009 -- Mock auction simulator (XL)
27. FEAT-012 -- Mobile responsive (L)
28. FEAT-013 -- Export results (S)
29. FEAT-014 -- Historical prices (M)

---

## Appendix A: File Reference

| File | Lines | Purpose | Key Issues |
|---|---|---|---|
| `backend/server.py` | ~1013 | FastAPI app, endpoints, WebSocket | Mega-function (PERF-001), partial WS handler (BUG-006), HTML in responses (QUAL-005) |
| `backend/state.py` | ~452 | Singleton draft state | O(n^2) VONA (PERF-002), singleton (QUAL-002) |
| `backend/engine.py` | ~324 | Pure math engine | Dead wrapper (QUAL-006) |
| `backend/config.py` | ~293 | Pydantic settings | -- |
| `backend/models.py` | ~196 | Data models | -- |
| `backend/ai_advisor.py` | ~484 | AI integration | Wrong labels (BUG-003), slot parsing (BUG-001), new client per call (PERF-003) |
| `backend/draft_plan.py` | ~423 | AI draft plan | Duplicate AI call functions |
| `backend/roster_optimizer.py` | ~167 | Greedy optimizer | -- |
| `backend/projections.py` | ~79 | CSV loader | Duplicate normalization (QUAL-001) |
| `backend/fuzzy_match.py` | ~143 | Name matching | Canonical normalization source |
| `backend/adp.py` | ~63 | ADP comparison | Duplicate normalization (QUAL-001) |
| `backend/opponent_model.py` | ~134 | Opponent tracking | -- |
| `backend/nomination.py` | ~209 | Nomination strategy | -- |
| `backend/sleeper_watch.py` | ~87 | Bargain targeting | -- |
| `backend/player_news.py` | ~218 | Player context | Hardcoded byes (BUG-002), linear scan (PERF-004) |
| `backend/ticker.py` | ~120 | Event feed | Singleton (QUAL-002) |
| `backend/what_if.py` | ~157 | Draft simulation | -- |
| `backend/grader.py` | ~64 | Post-draft grading | Docstring says "Gemini" |
| `backend/event_store.py` | ~90 | Event log | Seq counting (BUG-005), singleton (QUAL-002) |
| `extension/content.js` | ~1535 | Platform interceptor + overlay | Large file, no configuration |
| `extension/background.js` | ~256 | Service worker | Hardcoded URLs (SEC-003) |
| `extension/content-bridge.js` | ~134 | Message bridge | -- |
| `dashboard/src/App.jsx` | ~130 | React app root | No error boundaries (CHORE-006) |
| `dashboard/src/hooks/useDraftState.js` | ~43 | State management | -- |
| `dashboard/src/hooks/useWebSocket.js` | ~64 | WS client | -- |

## Appendix B: Glossary of Metrics

| Metric | Definition |
|---|---|
| VORP | Value Over Replacement Player: `projected_points - replacement_level` |
| VONA | Value Over Next Available: point gap to next-best undrafted at same position |
| FMV | Fair Market Value: `baseline_AAV x inflation_factor` |
| VOM | Value Over Market: `FMV - actual_sale_price` (positive = bargain) |
| PAR/$ | Points Above Replacement per Dollar: `VORP / price` |
| Inflation | `total_remaining_cash / total_remaining_AAV` |
| Scarcity | Tier-based premium: 50% drafted -> 1.05x, 70% -> 1.15x, 85% -> 1.30x |
