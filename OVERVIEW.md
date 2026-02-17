# Fantasy Auction Assistant — Project Overview

A real-time ESPN Fantasy Football auction draft assistant. A Chrome Extension scrapes ESPN's live draft state, a Python FastAPI backend crunches VORP/FMV/scarcity/inflation math, Gemini AI provides contextual advice, and a React dashboard visualizes everything.

```
┌─────────────────────┐     POST /draft_update      ┌──────────────────────┐
│   Chrome Extension   │ ──────────────────────────► │   FastAPI Backend    │
│   (content.js)       │ ◄────────────────────────── │   (server.py)        │
│                      │     advice JSON             │                      │
│  • React Fiber       │                             │  • VORP / FMV engine │
│    traversal         │                             │  • Gemini AI advisor │
│  • DOM fallback      │                             │  • Event sourcing    │
│  • Overlay UI        │                             │  • Opponent modeling │
│  • Watch list        │                             │  • Ticker + alerts   │
└─────────────────────┘                              └──────┬───────────────┘
                                                            │ WebSocket
                                                            ▼
                                                     ┌──────────────────────┐
                                                     │   React Dashboard    │
                                                     │   (Vite + daisyUI)   │
                                                     │                      │
                                                     │  • DraftBoard table  │
                                                     │  • Budget tracker    │
                                                     │  • Inflation chart   │
                                                     │  • Scarcity heatmap  │
                                                     │  • Live ticker feed  │
                                                     └──────────────────────┘
```

---

## Directory Structure

```
fantasy-auction-assistant/
├── backend/
│   ├── server.py            # FastAPI app — endpoints, WebSocket, SSE streaming
│   ├── state.py             # Singleton DraftState — tracks all players, teams, rosters
│   ├── engine.py            # Pure math engine — VORP, FMV, VONA, inflation, scarcity
│   ├── config.py            # Pydantic settings from .env — roster slots, sport profiles, draft strategies
│   ├── models.py            # Data models — DraftUpdate, PlayerState, EngineAdvice, etc.
│   ├── ai_advisor.py        # Gemini 1.5 Flash integration — contextual advice + streaming
│   ├── projections.py       # Multi-source CSV loader with weighted merging
│   ├── fuzzy_match.py       # RapidFuzz name resolution (ESPN names ↔ projections CSV)
│   ├── adp.py               # ADP auction values — consensus market comparison
│   ├── opponent_model.py    # Opponent roster tracking — positional needs + bidding war risk
│   ├── nomination.py        # Nomination strategy engine — drain / desperation / bargain
│   ├── sleeper_watch.py     # End-game $1–3 bargain targeting
│   ├── ticker.py            # Live event feed — rolling 50-event buffer
│   ├── dead_money.py        # Overpay detection — flags sales >30% above FMV
│   ├── what_if.py           # Draft simulation — "what if I spend $X on Player Y?"
│   ├── grader.py            # Post-draft AI grading — position grades, best/worst picks
│   ├── event_store.py       # Append-only JSONL event log for crash recovery
│   ├── requirements.txt
│   ├── .env                 # Configuration (API keys, league settings, roster slots)
│   └── data/
│       └── sheet_2026.csv   # Player projections (name, position, points, AAV, tier)
│
├── extension/
│   ├── manifest.json        # Manifest V3 — dual-world content scripts
│   ├── content.js           # MAIN world — React Fiber scraping + overlay UI
│   ├── content-bridge.js    # ISOLATED world — chrome.runtime message bridge
│   └── background.js        # Service worker — cookie extraction, server comms, health
│
└── dashboard/
    ├── src/
    │   ├── App.jsx
    │   ├── hooks/
    │   │   ├── useDraftState.js   # Fetches initial state + subscribes to WebSocket
    │   │   └── useWebSocket.js    # Persistent WS with auto-reconnect
    │   └── components/
    │       ├── Header.jsx         # Connection status, budget, inflation, strategy selector
    │       ├── CurrentAdvice.jsx  # Latest AI/engine recommendation
    │       ├── MyRoster.jsx       # Slot-by-slot roster display
    │       ├── DraftBoard.jsx     # Full player table with filters + search
    │       ├── BudgetTracker.jsx  # All-team budget comparison
    │       ├── InflationGraph.jsx # Recharts line chart over time
    │       ├── ScarcityHeatMap.jsx# Position-level supply remaining
    │       ├── TopRemaining.jsx   # Top 3 undrafted per position
    │       ├── NominationPanel.jsx# Strategic nomination suggestions
    │       ├── SleeperWatch.jsx   # Late-draft bargain candidates
    │       ├── OpponentNeeds.jsx  # Opponent positional needs matrix
    │       ├── ActivityFeed.jsx   # Live ticker event stream
    │       └── DeadMoneyAlert.jsx # Overpay warning banners
    ├── tailwind.config.js
    └── package.json
```

---

## Data Flow

1. **ESPN draft room** loads in Chrome. `content.js` injects into the page (MAIN world) and polls every 500ms.
2. **React Fiber traversal** walks ESPN's internal `__reactFiber$` tree to extract picks, nominations, bids, budgets, and rosters. Falls back to DOM scraping if the fiber isn't found.
3. Payload goes through `content-bridge.js` (ISOLATED world, has `chrome.runtime` access) → `background.js` (service worker), which attaches ESPN cookies (SWID, espn_s2).
4. **`POST /draft_update`** hits the FastAPI backend. The state singleton updates, the engine runs all calculations, Gemini is called (with a 400ms timeout), and a response is sent back.
5. The overlay in ESPN updates with the advice. Simultaneously, the backend **broadcasts a WebSocket snapshot** to the React dashboard.
6. Every state change is appended to `event_log.jsonl` so the entire draft can be replayed on restart.

---

## Backend Modules

### Calculation Engine (`engine.py`)

All pure math, no I/O. Called on every `/draft_update`.

| Metric | What It Does |
|---|---|
| **VORP** | `projected_points − replacement_level_points`. Replacement level = Nth-ranked player at that position (configurable via `VORP_BASELINE_*`). |
| **FMV** | `BaselineAAV × inflation`. The inflation-adjusted "true" price of a player right now. |
| **Inflation** | `total_remaining_cash / total_remaining_AAV` across all undrafted players. Starts near 1.0, climbs as money pools shrink slower than player supply. |
| **VONA** | `player.projected_points − next_best_undrafted.projected_points` at the same position. Measures positional scarcity: high VONA = big drop-off if you miss this player. |
| **Scarcity Multiplier** | Tier-based shortage premium. When 70%+ of a tier is drafted → 1.15×, 85%+ → 1.3×. Applied to FMV. |
| **Need Multiplier** | Roster fit scoring. 0.0 = no slot (hard PASS), 0.5 = flex-only, 1.0 = starter slot open, 1.2 = last starter slot at that position. |
| **Strategy Multiplier** | Draft strategy bias combining `position_weight × tier_weight` from the active strategy profile. Adjusts FMV and optimizer VORP/$ ratios. |

The engine combines these into an **action recommendation**:
- **BUY** — bid ≤ adjusted FMV, positive VORP, open roster slot → suggested bid returned
- **PASS** — no slot, bid >15% above FMV, or negative VORP
- **PRICE_ENFORCE** — bid slightly above FMV (up to +10%), worth pushing price up to drain opponent budgets

### Draft Strategy Profiles (`config.py`)

Configurable draft philosophies that bias the entire system — engine advice, optimizer, what-if, nominations, and AI context. Switchable at runtime via `POST /strategy` or the dashboard header dropdown.

| Strategy | Key Idea | Effect |
|---|---|---|
| **Balanced** | No bias (default) | All multipliers 1.0 |
| **Studs & Duds** | Spend 70%+ on 2-3 elite players | T1-T2 boosted, T3+ discounted |
| **RB Heavy** | Prioritize running backs | RB 1.3×, others slightly reduced |
| **WR Heavy** | Prioritize wide receivers | WR 1.3×, others slightly reduced |
| **Elite TE** | Pay premium for a top tight end | TE 1.35×, T1-T2 boosted |

Each strategy defines position weights and tier weights. The combined multiplier `position_weight × tier_weight` is applied to:
- **Engine advice** — adjusts FMV and action thresholds
- **Roster optimizer** — biases VORP/$ ratio in greedy fill
- **What-if simulator** — same VORP/$ bias
- **Nomination engine** — shifts priority toward/away from strategy positions
- **AI advisor** — strategy context injected into the prompt

### AI Advisor (`ai_advisor.py`)

Wraps Gemini 1.5 Flash with rich draft context:

- Current engine advice (FMV, VORP, VONA, action)
- Opponent positional needs + bidding war risk flags
- Recent picks with prices (trend detection)
- Top remaining players by position
- ADP vs FMV comparison
- My roster state + remaining budget
- Team synergy notes

The AI call has a **400ms timeout** — if Gemini is slow, the response falls back to engine-only advice (no delay to the user). Responses are cached for 10 seconds with bid-bucketed keys to avoid redundant calls.

**SSE streaming** (`GET /stream/{player}`) provides progressive AI output for the overlay's streaming display.

### State Manager (`state.py`)

A singleton that holds the entire draft in memory:

- **Player pool** — all ~136 players loaded from CSV, each with draft status, price, buyer
- **Team budgets** — per-team remaining cash, tracked in real-time
- **My roster** — slot-by-slot view (QB1, RB1, RB2, FLEX1, etc.) with auto-assignment
- **Opponent rosters** — parsed from ESPN roster data, fed into opponent model
- **Inflation history** — timestamped series for the dashboard chart
- **VONA cache** — pre-computed for every undrafted player on each update
- **Replacement levels** — recalculated as players are drafted

Key behaviors:
- **Fuzzy name matching** reconciles ESPN display names with projections CSV (handles "A.J. Brown" → "AJ Brown", "Patrick Mahomes II" → "Patrick Mahomes", suffix stripping)
- **Event replay** on startup from `event_log.jsonl` restores full state after crashes
- **Reset** command wipes state for a fresh draft

### Opponent Model (`opponent_model.py`)

Analyzes all non-user teams:

- **Positional needs** — which positions each team still needs starters at
- **Bidding war risk** — flagged when `teams_needing_position / players_remaining ≥ 75%`
- **Spending power** — `remaining_budget − remaining_roster_holes` (effective per-player budget)

This feeds into the AI advisor context and the nomination engine.

### Nomination Strategy (`nomination.py`)

Three distinct strategies, priority-ranked:

| Strategy | Goal | Example |
|---|---|---|
| **BUDGET_DRAIN** | Nominate expensive players you don't need | Force rivals to spend on elite RBs when you're stacked at RB |
| **RIVAL_DESPERATION** | Nominate scarce positions you've filled | Start bidding wars at positions where supply is thin |
| **BARGAIN_SNAG** | Nominate cheap players you need | Grab $5–10 guys quietly at positions you're thin |

### Sleeper Watch (`sleeper_watch.py`)

Identifies end-of-draft bargain targets ($1–3 players):

- Positive VORP (actually has fantasy value)
- FMV between $3–25 (not a kicker, not an elite player)
- Most teams are budget-constrained (can't afford to bid up)

**Sleeper score** = `VORP × 0.4 + constraint_ratio × 20 + price_discount × 10`

### Live Ticker (`ticker.py`)

Rolling 50-event buffer with 6 event types:

| Event | Trigger |
|---|---|
| `NEW_NOMINATION` | Player put on the block |
| `BID_PLACED` | New high bid detected |
| `PLAYER_SOLD` | Bidding closes |
| `BUDGET_ALERT` | Team drops below $15 remaining |
| `DEAD_MONEY` | Sale >30% above FMV (overpay) |
| `MARKET_SHIFT` | Inflation changes >0.5% on a single sale |

Events are deduped by type + player + bid to avoid noise.

### Dead Money Detection (`dead_money.py`)

Flags overpays where `draft_price > FMV × 1.30`. Captures the **pre-sale inflation** so the FMV comparison is accurate (inflation recalculates after each sale). Tracks the inflation delta caused by the overpay.

### What-If Simulator (`what_if.py`)

`GET /whatif?player=Saquon Barkley&price=70`

Deep-clones the draft state, simulates buying the player at the given price, then **greedily fills the rest of your roster** by best VORP/$ ratio. Returns projected total points and the optimal remaining picks.

### Post-Draft Grader (`grader.py`)

`GET /grade`

Sends your full roster with surplus values (BaselineAAV − price) to Gemini with a 10-second timeout. Returns:
- Overall letter grade (A+ to F)
- Per-position grades
- Best and worst picks with reasoning
- Waiver wire targets for weak spots

### Event Sourcing (`event_store.py`)

Every `/draft_update` and `/manual` call is appended to `event_log.jsonl` with a sequence number. On startup, the entire log is replayed to reconstruct state. This means the server can crash mid-draft and pick up exactly where it left off.

---

## Chrome Extension

### Architecture (Manifest V3)

ESPN's Content Security Policy blocks inline scripts, so the extension uses a **dual-world injection pattern**:

```
┌─ MAIN world ──────────────┐    window.postMessage    ┌─ ISOLATED world ────────────┐
│  content.js                │ ───────────────────────► │  content-bridge.js           │
│  • Can access React Fiber  │                          │  • Has chrome.runtime        │
│  • Can read page JS state  │ ◄─────────────────────── │  • Relays to background.js   │
│  • Renders overlay UI      │    window.postMessage     │                              │
└────────────────────────────┘                          └──────────────────────────────┘
                                                                    │
                                                        chrome.runtime.sendMessage
                                                                    ▼
                                                        ┌──────────────────────────┐
                                                        │  background.js           │
                                                        │  • Reads ESPN cookies    │
                                                        │  • POST to backend       │
                                                        │  • Health polling (5s)   │
                                                        │  • SSE streaming proxy   │
                                                        └──────────────────────────┘
```

### ESPN Scraping (`content.js`)

The extension finds ESPN's React root and walks the `__reactFiber$` tree to extract:

- `draftDetail.picks` — completed draft picks
- `draftDetail.currentPick` — active nomination (player, bid, bidder)
- `teams[].remainingBudget` — all team budgets
- `rosters` — full roster assignments per team
- `players` map — player metadata (name, position, slot IDs)

If the fiber tree isn't accessible (ESPN DOM update, race condition), it falls back to **DOM selectors** for the nomination bar, bid amount, and team list.

Polling runs every **500ms** with hash-based deduplication — if the state hasn't changed, no request is sent.

### Overlay UI

A draggable, resizable panel injected into the ESPN draft page:

- **3-state minimize**: full panel → compact header → hidden
- **Live advice**: color-coded action (green = BUY, red = PASS, yellow = PRICE_ENFORCE)
- **Suggested bid** with max bid ceiling
- **Manual input** — type commands: `sold PlayerName 45`, `undo PlayerName`, `watch PlayerName`, `whatif PlayerName 50`
- **Watch list** — tracked players trigger an audio alert (880Hz beep) + border flash when nominated
- **Mini roster** — your current roster slots
- **Top remaining** — best available per position
- **Live ticker** — scrolling event feed with type badges
- **Dead money flash** — red border pulse on overpay detection

### Background Service Worker (`background.js`)

- Reads ESPN's `SWID` and `espn_s2` cookies, attaches them to backend requests
- 5-second health polling to `/health` — broadcasts connection status to all tabs
- SSE streaming proxy — connects to `/stream/{player}` with an AbortController
- Forwards manual override commands to `/manual`

---

## React Dashboard

**Stack**: Vite + React 18 + Tailwind CSS + daisyUI + Recharts

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Header: strategy │ budget │ inflation │ picks │ AI status     │
├────────────────┬────────────────┬──────────────┬────────────────┤
│ CurrentAdvice  │  MyRoster      │ TopRemaining │ ActivityFeed   │
│ (latest rec)   │  (slot view)   │ (by pos)     │ (live ticker)  │
├────────────────┼────────────────┼──────────────┼────────────────┤
│ BudgetTracker  │ InflationGraph │ ScarcityMap  │ NominationPanel│
│ (all teams)    │ (line chart)   │ (heatmap)    │ (suggestions)  │
├────────────────┴────────────────┼──────────────┴────────────────┤
│ SleeperWatch                    │ OpponentNeeds                  │
│ (bargain targets)               │ (positional needs matrix)      │
├─────────────────────────────────┴────────────────────────────────┤
│ DraftBoard (full player table — filter by position, search)      │
│ Columns: Player, Pos, Tier, FMV, VORP, VONA, Price              │
└──────────────────────────────────────────────────────────────────┘
```

### Real-Time Updates

`useDraftState` hook fetches initial state from `GET /dashboard/state`, then subscribes to `ws://localhost:8000/ws`. Every `/draft_update` the backend processes triggers a WebSocket broadcast with the full state snapshot. Components re-render instantly.

Auto-reconnect with 2-second delay on disconnect.

---

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(none)* | Optional — runs engine-only if not set |
| `MY_TEAM_NAME` | `"My Team"` | Your team name as it appears on ESPN |
| `LEAGUE_SIZE` | `10` | Number of teams in the league |
| `BUDGET` | `200` | Starting auction budget per team |
| `ROSTER_SLOTS` | `QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF` | Comma-separated roster slots |
| `SPORT` | `"football"` | `football`, `basketball`, or `auto` |
| `DRAFT_STRATEGY` | `balanced` | Draft philosophy: `balanced`, `studs_and_duds`, `rb_heavy`, `wr_heavy`, `elite_te` |
| `CSV_PATH` | `data/sheet_2026.csv` | Player projections file |
| `CSV_PATHS` | *(none)* | Multi-source: `path1,path2,path3` |
| `PROJECTION_WEIGHTS` | *(none)* | Weights per source: `0.5,0.3,0.2` |
| `ADP_CSV_PATH` | *(none)* | ADP auction values for comparison |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Which Gemini model to use |
| `AI_TIMEOUT_MS` | `400` | Max wait for AI response (ms) |
| `VORP_BASELINE_QB` | `11` | Replacement level rank for QB |
| `VORP_BASELINE_RB` | `30` | Replacement level rank for RB |
| `VORP_BASELINE_WR` | `30` | Replacement level rank for WR |
| `VORP_BASELINE_TE` | `11` | Replacement level rank for TE |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/draft_update` | Receive ESPN state from extension, return advice |
| `POST` | `/manual` | Manual commands: sold, budget, undo, nom, suggest, whatif |
| `POST` | `/strategy` | Set active draft strategy profile |
| `GET` | `/advice?player=...` | AI-enhanced advice for a specific player |
| `GET` | `/health` | Heartbeat for connection monitoring |
| `GET` | `/opponents` | Opponent positional needs analysis |
| `GET` | `/sleepers` | End-game bargain targets |
| `GET` | `/nominate` | Nomination strategy suggestions |
| `GET` | `/whatif?player=...&price=...` | Draft simulation |
| `GET` | `/grade` | Post-draft AI grading |
| `GET` | `/stream/{player}` | SSE streaming AI advice |
| `GET` | `/dashboard/state` | Full state snapshot for dashboard |
| `WS` | `/ws` | Real-time updates to dashboard |

---

## Quick Start

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
cp .env.example .env        # Edit with your settings
uvicorn server:app --host 0.0.0.0 --port 8000 --reload

# 2. Dashboard
cd dashboard
npm install
npm run dev                 # http://localhost:5173

# 3. Extension
# Chrome → chrome://extensions → Developer Mode → Load unpacked → select extension/
# Navigate to your ESPN auction draft room — overlay appears automatically
```
