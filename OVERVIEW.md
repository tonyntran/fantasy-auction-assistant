# Fantasy Auction Assistant — Project Overview

A real-time fantasy football auction draft assistant built primarily for the Sleeper platform (with ESPN support). A Chrome extension intercepts Sleeper's live WebSocket data, a Python FastAPI backend runs VORP/FMV/scarcity/inflation math, Claude AI provides strategic advice, and a React dashboard visualizes everything.

```
┌─────────────────────┐     POST /draft_update      ┌──────────────────────┐
│   Chrome Extension   │ ──────────────────────────► │   FastAPI Backend    │
│   (content.js)       │ ◄────────────────────────── │   (server.py)        │
│                      │     advice JSON             │                      │
│  • Sleeper WS        │                             │  • VORP / FMV engine │
│    interceptor       │                             │  • Claude AI advisor │
│  • ESPN Fiber        │                             │  • Event sourcing    │
│    fallback          │                             │  • Opponent modeling │
│  • Overlay UI        │                             │  • Ticker + alerts   │
└─────────────────────┘                              └──────┬───────────────┘
                                                            │ WebSocket
                                                            ▼
                                                     ┌──────────────────────┐
                                                     │   React Dashboard    │
                                                     │   (Vite + daisyUI)   │
                                                     │                      │
                                                     │  • DraftBoard table  │
                                                     │  • Roster optimizer  │
                                                     │  • AI draft plan     │
                                                     │  • Budget tracker    │
                                                     │  • Scarcity heatmap  │
                                                     │  • VOM leaderboard   │
                                                     │  • Live ticker feed  │
                                                     └──────────────────────┘
```

---

## Directory Structure

```
fantasy-auction-assistant/
├── backend/
│   ├── server.py            # FastAPI app — endpoints, WebSocket, event broadcasting
│   ├── state.py             # Singleton DraftState — tracks all players, teams, rosters
│   ├── engine.py            # Pure math engine — VORP, FMV, VONA, inflation, scarcity
│   ├── config.py            # Pydantic settings from .env — roster slots, sport profiles, strategies
│   ├── models.py            # Data models — DraftUpdate, PlayerState, EngineAdvice, MyTeamState
│   ├── ai_advisor.py        # Claude/Gemini integration — contextual advice with caching
│   ├── draft_plan.py        # On-demand AI draft plan — spending strategy, key targets, bargains
│   ├── roster_optimizer.py  # Two-phase optimizer — starters by VORP/$, bench at $1 each
│   ├── projections.py       # Multi-source CSV loader with weighted merging
│   ├── fuzzy_match.py       # RapidFuzz name resolution (platform names ↔ projections CSV)
│   ├── adp.py               # ADP auction values — consensus market comparison
│   ├── opponent_model.py    # Opponent roster tracking — positional needs + bidding war risk
│   ├── nomination.py        # Nomination strategy engine — drain / desperation / bargain
│   ├── sleeper_watch.py     # End-game $1–3 bargain targeting
│   ├── player_news.py       # Injury/status data from Sleeper's player database
│   ├── ticker.py            # Live event feed — rolling 50-event buffer
│   ├── what_if.py           # Draft simulation — "what if I spend $X on Player Y?"
│   ├── grader.py            # Post-draft AI grading — position grades, best/worst picks
│   ├── event_store.py       # Append-only JSONL event log for crash recovery
│   ├── requirements.txt
│   ├── .env                 # Configuration (API keys, league settings, roster slots)
│   └── data/
│       └── sheet_2026.csv   # Player projections (name, position, points, AAV, tier)
│
├── extension/
│   ├── manifest.json        # Manifest V3 — Sleeper + ESPN content scripts
│   ├── content.js           # MAIN world — Sleeper WS interceptor, ESPN Fiber scraping, overlay UI
│   ├── content-bridge.js    # ISOLATED world — chrome.runtime message bridge
│   └── background.js        # Service worker — cookie extraction, server comms, health polling
│
└── dashboard/
    ├── src/
    │   ├── App.jsx
    │   ├── hooks/
    │   │   ├── useDraftState.js   # Fetches initial state + subscribes to WebSocket
    │   │   └── useWebSocket.js    # Persistent WS with auto-reconnect
    │   └── components/
    │       ├── Header.jsx          # Connection status, budget, inflation, strategy selector
    │       ├── CurrentAdvice.jsx   # Latest AI/engine recommendation with player news
    │       ├── MyRoster.jsx        # Slot-by-slot roster display (starters + bench)
    │       ├── DraftBoard.jsx      # Full player table with filters, search, and news badges
    │       ├── TeamOverview.jsx    # All-team budget comparison + opponent needs
    │       ├── ScarcityHeatMap.jsx # Position/tier supply remaining
    │       ├── TopRemaining.jsx    # Top undrafted per position
    │       ├── RosterOptimizer.jsx # Optimal picks + AI draft plan with staleness tracking
    │       ├── VomLeaderboard.jsx  # Value Over Market — biggest bargains and overpays
    │       ├── NominationPanel.jsx # Strategic nomination suggestions
    │       ├── SleeperWatch.jsx    # Late-draft bargain candidates
    │       └── ActivityFeed.jsx    # Live ticker event stream
    ├── tailwind.config.js
    └── package.json
```

---

## Data Flow

1. **Sleeper draft room** loads in Chrome. `content.js` injects into the page (MAIN world) and installs a **WebSocket interceptor** that captures Sleeper's real-time draft messages (picks, bids, nominations, rosters). For ESPN, it polls React Fiber state every 500ms as a fallback.
2. Payload goes through `content-bridge.js` (ISOLATED world, has `chrome.runtime` access) → `background.js` (service worker).
3. **`POST /draft_update`** hits the FastAPI backend. The state singleton updates, the engine runs all calculations, Claude AI is called asynchronously, and a response is sent back.
4. The overlay on the draft page updates with the advice. Simultaneously, the backend **broadcasts a WebSocket snapshot** to the React dashboard.
5. Every state change is appended to `event_log.jsonl` so the entire draft can be replayed on restart.

---

## Backend Modules

### Calculation Engine (`engine.py`)

All pure math, no I/O. Called on every `/draft_update`.

| Metric | What It Does |
|---|---|
| **VORP** | `projected_points − replacement_level_points`. Replacement level = Nth-ranked player at that position (configurable via `VORP_BASELINE_*`). |
| **FMV** | `BaselineAAV × inflation`. The inflation-adjusted "true" price of a player right now. |
| **Inflation** | `total_remaining_cash / total_remaining_AAV` across all undrafted players. Starts near 1.0, climbs as money pools shrink slower than player supply. |
| **VONA** | `player.projected_points − next_best_undrafted.projected_points` at the same position. Measures positional scarcity: high VONA = big gap — don't let this player slip. |
| **Scarcity Multiplier** | Tier-based shortage premium. When 50%+ of a tier is drafted → 1.05×, 70%+ → 1.15×, 85%+ → 1.3×. Applied to FMV. |
| **Need Multiplier** | Binary roster fit: 1.0 = starter slot open, 0.0 = only bench or no slot. BENCH slots don't drive bidding — bench is filled at $1 at the end. |
| **Strategy Multiplier** | Draft strategy bias: `position_weight × tier_weight` from the active profile. Adjusts FMV and optimizer VORP/$ ratios. |

The engine produces two FMV values:
- **Adjusted FMV** = `FMV × scarcity × need × strategy` — used for bid logic (whether to buy or pass)
- **Market FMV** = `FMV × scarcity × strategy` — displayed to the user (what the player is worth on the open market regardless of your roster)

Action recommendations:
- **BUY** — bid at or below adjusted FMV, positive VORP, starter slot open
- **PASS** — no starter slot, bid >15% above FMV, negative VORP, or bench-only
- **PRICE_ENFORCE** — no starter need but player going below market FMV; bid up to deny a bargain and drain opponent budgets

### Draft Strategy Profiles (`config.py`)

Configurable draft philosophies that bias the entire system. Switchable at runtime via `POST /strategy` or the dashboard header dropdown.

| Strategy | Key Idea | Effect |
|---|---|---|
| **Balanced** | No bias (default) | All multipliers 1.0 |
| **Studs & Steals** | Pay premium for 2-3 elite starters, then hunt undervalued sleepers with upside catalysts | T1 1.15×, T2 1.05×, T3-T5 discounted |
| **RB Heavy** | Prioritize running backs | RB 1.3×, others slightly reduced |
| **WR Heavy** | Prioritize wide receivers | WR 1.3×, others slightly reduced |
| **Elite TE** | Pay premium for a top tight end | TE 1.35×, T1-T2 boosted |

For Studs & Steals specifically, the AI advisor injects tier-aware guidance: aggressive pursuit of Tier 1 players, and upside catalyst evaluation (new role, coaching scheme, breakout trajectory) for Tier 2+ players flagged as potential steals.

### AI Advisor (`ai_advisor.py`)

Supports Claude (Anthropic API) and Gemini, configurable via `AI_PROVIDER`. Claude is the primary provider.

Context sent to the AI on each nomination:
- Current engine advice (FMV, VORP, VONA, action)
- Opponent positional needs + bidding war risk flags
- Recent picks with prices (trend detection)
- Top remaining players by position
- ADP vs FMV comparison
- My roster state + remaining budget
- Draft strategy context with tier-specific guidance

The AI call has a configurable timeout (`AI_TIMEOUT_MS`, default 8s). If the AI is slow, the response falls back to engine-only advice. Responses are cached for 120 seconds per player to avoid redundant calls. Rate limiting is handled with a 60-second backoff on 429 responses.

### AI Draft Plan (`draft_plan.py`)

On-demand strategic spending plan triggered by button click in the dashboard. Synthesizes optimizer output with AI analysis of market dynamics, opponent pressure, and spending allocation.

The prompt uses **starter-only needs** (bench excluded) and calculates a spendable budget after reserving $1 per bench spot. The AI returns structured JSON:

- **Strategy summary** — 2-3 sentence overview
- **Spending plan** — budget allocation per position with tier targets
- **Key targets** — 3-5 premium players with price ranges and priority levels
- **Bargain picks** — 1-2 value sleepers with upside reasoning
- **Avoid list** — players to let opponents overpay for
- **Budget reserve** — minimal ($1 per bench spot)

Cached with staleness tracking — invalidated when any player is drafted. The dashboard shows a freshness badge (Fresh / N picks ago).

### Roster Optimizer (`roster_optimizer.py`)

Two-phase greedy fill:

1. **Phase 1: Starters** — Fill all starter slots (QB, RB, WR, TE, FLEX, K, DEF) by best VORP/$ ratio, using the starter-only budget (total minus $1 per bench spot)
2. **Phase 2: Bench** — Fill 6 bench spots at $1 each with the highest remaining VORP players

Returns starter picks, bench picks, cost breakdown, and projected points.

### State Manager (`state.py`)

A singleton that holds the entire draft in memory:

- **Player pool** — all ~140 players loaded from CSV, each with draft status, price, buyer
- **Team budgets** — per-team remaining cash, tracked in real-time
- **My roster** — slot-by-slot view (QB, RB1, RB2, FLEX1, FLEX2, BENCH1-6, etc.) with auto-assignment
- **Slot priority** — when assigning a drafted player: dedicated slot > flex/superflex > bench
- **Opponent rosters** — parsed from platform roster data, fed into opponent model
- **Inflation history** — timestamped series for tracking over time
- **VONA cache** — pre-computed for every undrafted player on each update

Key behaviors:
- **Fuzzy name matching** — RapidFuzz reconciles platform display names with projections CSV
- **Event replay** on startup from `event_log.jsonl` restores full state after crashes
- **Starter vs bench need** — `get_starter_need()` excludes bench slots for engine/optimizer use; `get_positional_need()` includes all slots
- **Team aliases** — map platform team IDs to display names

### Opponent Model (`opponent_model.py`)

Analyzes all non-user teams:

- **Positional needs** — which positions each team still needs starters at
- **Bidding war risk** — flagged when `teams_needing_position / players_remaining ≥ 75%`
- **Spending power** — `remaining_budget − remaining_roster_holes` (effective per-player budget)

Feeds into AI advisor context, nomination engine, and the AI draft plan.

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

### Player News (`player_news.py`)

Fetches injury and status data from the Sleeper player database API. Cached for 30 minutes. Surfaces injury designations, status changes, and news blurbs on the draft board and current advice panel.

### Live Ticker (`ticker.py`)

Rolling 50-event buffer with event types:

| Event | Trigger |
|---|---|
| `NEW_NOMINATION` | Player put on the block |
| `BID_PLACED` | New high bid detected |
| `PLAYER_SOLD` | Bidding closes — shows sale price vs FMV |
| `BUDGET_ALERT` | Team drops below critical budget threshold |
| `MARKET_SHIFT` | Inflation changes >0.5% on a single sale |

Events are deduped by type + player + bid to avoid noise.

### What-If Simulator (`what_if.py`)

`GET /whatif?player=Saquon Barkley&price=70`

Deep-clones the draft state, simulates buying the player at the given price, then greedily fills the rest of your starter roster by best VORP/$ ratio (reserving $1 per bench spot). Returns projected total points and the optimal remaining picks.

### Post-Draft Grader (`grader.py`)

`GET /grade`

Sends your full roster with surplus values (BaselineAAV − price) to Claude. Returns:
- Overall letter grade (A+ to F)
- Per-position grades
- Best and worst picks with reasoning
- Waiver wire targets for weak spots

Falls back to engine-only grade (points + surplus totals) if AI is unavailable.

### Event Sourcing (`event_store.py`)

Every `/draft_update` and `/manual` call is appended to `event_log.jsonl` with a sequence number. On startup, the entire log is replayed to reconstruct state. The server can crash mid-draft and pick up exactly where it left off.

---

## Chrome Extension

### Architecture (Manifest V3)

The extension uses a **dual-world injection pattern** to bridge page context with Chrome APIs:

```
┌─ MAIN world ──────────────┐    window.postMessage    ┌─ ISOLATED world ────────────┐
│  content.js                │ ───────────────────────► │  content-bridge.js           │
│  • Sleeper WS interceptor  │                          │  • Has chrome.runtime        │
│  • ESPN React Fiber access │ ◄─────────────────────── │  • Relays to background.js   │
│  • Renders overlay UI      │    window.postMessage     │                              │
└────────────────────────────┘                          └──────────────────────────────┘
                                                                    │
                                                        chrome.runtime.sendMessage
                                                                    ▼
                                                        ┌──────────────────────────┐
                                                        │  background.js           │
                                                        │  • POST to backend       │
                                                        │  • Health polling (5s)   │
                                                        │  • Cookie extraction     │
                                                        └──────────────────────────┘
```

### Sleeper Integration (`content.js`)

The extension intercepts Sleeper's WebSocket connection by patching the global `WebSocket` constructor before Sleeper's JavaScript loads (`run_at: "document_start"`). This captures real-time draft messages:

- **Picks/sales** — player name, price, team
- **Nominations** — current player on the block
- **Bids** — live bid updates
- **Rosters** — full roster state per team
- **Budgets** — remaining cash per team

### ESPN Fallback

For ESPN draft rooms, `content.js` walks the `__reactFiber$` tree to extract picks, nominations, bids, budgets, and rosters. Falls back to DOM scraping if the fiber tree isn't accessible.

Polling runs every 500ms with hash-based deduplication — if the state hasn't changed, no request is sent.

### Overlay UI

A panel injected into the draft page with inline styles:

- **Nomination + bid info** at the top
- **Live advice** — color-coded action (green = BUY, red = PASS, yellow = PRICE_ENFORCE) with FMV, VORP, VONA
- **Strategy badge** — shows the active draft strategy
- **Manual input** — type commands: `sold PlayerName 45`, `undo PlayerName`, `nom PlayerName`, `whatif PlayerName 50`, `suggest`
- **Watch list** — tracked players trigger a beep + border flash when nominated
- **Live ticker** — scrolling event feed

---

## React Dashboard

**Stack**: Vite + React 18 + Tailwind CSS + daisyUI

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Header: strategy selector │ budget │ inflation │ picks │ AI status          │
├───────────────────┬─────────────────┬──────────────────┬─────────────────────┤
│ CurrentAdvice     │  TopRemaining   │  ActivityFeed    │ RosterOptimizer     │
│ (latest rec +     │  (top undrafted │  (live ticker)   │ (optimal picks +    │
│  player news)     │   by position)  │                  │  AI draft plan,     │
├───────────────────┼─────────────────┼──────────────────┤  sticky sidebar)    │
│ MyRoster          │  TeamOverview   │  ScarcityHeatMap │                     │
│ (starters + bench │  (budgets +     │  (pos/tier grid) │                     │
│  with separator)  │   opp needs)    │                  │                     │
├───────────────────┼─────────────────┼──────────────────┤                     │
│ VomLeaderboard    │  SleeperWatch   │  NominationPanel │                     │
│ (bargains/overpay)│  (endgame $1-3) │  (nom strategy)  │                     │
├───────────────────┴─────────────────┴──────────────────┴─────────────────────┤
│ DraftBoard (full player table — filter by position, search, news badges)     │
│ Columns: Player, Pos, Tier, Pts, FMV, VORP, VONA, Status, Price, Buyer      │
├──────────────────────────────────────────────────────────────────────────────┤
│ Glossary (VORP, VONA, FMV, Inflation, VOM definitions + value scales)        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Real-Time Updates

`useDraftState` hook fetches initial state from `GET /dashboard/state`, then subscribes to `ws://localhost:8000/ws`. Every `/draft_update` the backend processes triggers a WebSocket broadcast with the full state snapshot. Components re-render instantly. Auto-reconnect with 2-second delay on disconnect.

---

## Roster Configuration

The roster is defined by `ROSTER_SLOTS` in `.env`:

```
ROSTER_SLOTS=QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF,BENCH,BENCH,BENCH,BENCH,BENCH,BENCH
```

This produces 16 slots: 10 starters + 6 bench. The system treats starter and bench slots differently:

- **Starters** (QB, RB, WR, TE, FLEX, K, DEF) — drive bidding recommendations, optimizer allocates budget
- **BENCH** — accepts all positions, filled at $1 each at the end, does not drive engine advice

Slot eligibility controls which positions each slot type accepts:
- `QB/RB/WR/TE/K/DEF` — accept only their position
- `FLEX` — accepts RB, WR, TE
- `SUPERFLEX` — accepts QB, RB, WR, TE
- `BENCH` — accepts all positions

When a player is drafted to your team, slot assignment follows priority: **dedicated slot > flex > bench**.

---

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `AI_PROVIDER` | `"gemini"` | `claude` or `gemini` |
| `ANTHROPIC_API_KEY` | *(none)* | Claude API key (required if `AI_PROVIDER=claude`) |
| `GEMINI_API_KEY` | *(none)* | Gemini API key (required if `AI_PROVIDER=gemini`) |
| `PLATFORM` | `"espn"` | `sleeper` or `espn` — auto-detected from extension |
| `MY_TEAM_NAME` | `"My Team"` | Your team name as shown on the platform (comma-separated for aliases) |
| `LEAGUE_SIZE` | `10` | Number of teams in the league |
| `BUDGET` | `200` | Starting auction budget per team |
| `ROSTER_SLOTS` | `QB,RB,RB,...,BENCH×6` | Comma-separated roster slots |
| `SPORT` | `"football"` | `football`, `basketball`, or `auto` |
| `DRAFT_STRATEGY` | `balanced` | `balanced`, `studs_and_steals`, `rb_heavy`, `wr_heavy`, `elite_te` |
| `CSV_PATH` | `data/sheet_2026.csv` | Player projections file |
| `CSV_PATHS` | *(none)* | Multi-source: `path1,path2,path3` |
| `PROJECTION_WEIGHTS` | *(none)* | Weights per source: `0.5,0.3,0.2` |
| `ADP_CSV_PATH` | *(none)* | ADP auction values for market comparison |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model for per-player advice |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model (if using Gemini) |
| `AI_TIMEOUT_MS` | `8000` | Max wait for AI response (ms) |
| `VORP_BASELINE_QB` | `11` | Replacement level rank for QB |
| `VORP_BASELINE_RB` | `30` | Replacement level rank for RB |
| `VORP_BASELINE_WR` | `30` | Replacement level rank for WR |
| `VORP_BASELINE_TE` | `11` | Replacement level rank for TE |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/draft_update` | Receive platform state from extension, return advice |
| `POST` | `/manual` | Manual commands: sold, budget, undo, nom, suggest, whatif |
| `POST` | `/strategy` | Set active draft strategy profile |
| `POST` | `/team_aliases` | Set team display name aliases |
| `GET` | `/advice?player=...` | AI-enhanced advice for a specific player |
| `GET` | `/health` | Heartbeat for connection monitoring |
| `GET` | `/opponents` | Opponent positional needs analysis |
| `GET` | `/sleepers` | End-game bargain targets |
| `GET` | `/nominate` | Nomination strategy suggestions |
| `GET` | `/whatif?player=...&price=...` | Draft simulation |
| `GET` | `/grade` | Post-draft AI grading |
| `GET` | `/optimize` | Optimal remaining picks |
| `GET` | `/draft-plan` | On-demand AI draft plan with spending analysis |
| `GET` | `/dashboard/state` | Full state snapshot for dashboard |
| `GET` | `/state` | Debug state summary |
| `GET` | `/team_aliases` | View current team aliases |
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
# Navigate to your Sleeper auction draft room — overlay appears automatically
```
