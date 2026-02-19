# Fantasy Auction Assistant

A real-time fantasy football auction draft assistant built for the Sleeper platform (with ESPN support). A Chrome extension intercepts Sleeper's live WebSocket data, a Python FastAPI backend runs VORP/FMV/scarcity math, Claude AI provides strategic advice, and a React dashboard visualizes everything in real time.

```
Chrome Extension ──► FastAPI Backend ──► React Dashboard
(Sleeper WebSocket)   (engine + Claude)   (live via WebSocket)
```

## Features

- **Live draft interception** — WebSocket interceptor captures Sleeper's real-time auction data (ESPN React Fiber scraping also supported)
- **Auction math engine** — VORP, VONA, FMV, inflation tracking, positional scarcity, and roster-fit scoring
- **AI-powered advice** — Claude (Anthropic API) with full draft context, falling back to engine-only on timeout
- **BUY / PASS / PRICE_ENFORCE** recommendations with suggested bid amounts
- **AI Draft Plan** — on-demand strategic spending plan with key targets, price ranges, and budget allocation
- **Roster optimizer** — two-phase fill: starters by VORP/$, bench at $1 each
- **Opponent modeling** — positional needs, bidding war risk, spending power analysis
- **Draft strategy profiles** — Balanced, Studs & Steals, RB Heavy, WR Heavy, Elite TE — switchable at runtime
- **Nomination strategy** — budget drain, rival desperation, and bargain snag suggestions
- **What-if simulator** — project your roster if you win a player at a given price
- **VOM Leaderboard** — Value Over Market tracking for all drafted players
- **Player news** — injury and status data from Sleeper's player database
- **Post-draft grading** — AI-generated letter grades per position with waiver wire targets
- **Real-time dashboard** — draft board, budget tracker, scarcity heatmap, ticker feed, and more

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Edit with your settings
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev  # http://localhost:5173
```

### Chrome Extension

1. Go to `chrome://extensions`
2. Enable **Developer Mode**
3. Click **Load unpacked** and select the `extension/` directory
4. Navigate to your Sleeper auction draft room — the overlay appears automatically

## Configuration

Key `.env` variables:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(none)* | Claude API key — runs engine-only if not set |
| `AI_PROVIDER` | `"claude"` | `claude` or `gemini` |
| `PLATFORM` | `"sleeper"` | `sleeper` or `espn` |
| `MY_TEAM_NAME` | `"My Team"` | Your team name (comma-separated for aliases) |
| `LEAGUE_SIZE` | `10` | Number of teams |
| `BUDGET` | `200` | Starting auction budget per team |
| `ROSTER_SLOTS` | `QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF,BENCH×6` | Roster structure |
| `DRAFT_STRATEGY` | `balanced` | `balanced`, `studs_and_steals`, `rb_heavy`, `wr_heavy`, `elite_te` |

See [OVERVIEW.md](OVERVIEW.md) for the full configuration reference, architecture details, and API documentation.

## Tech Stack

- **Backend**: Python, FastAPI, Pydantic, Anthropic Claude API
- **Dashboard**: React 18, Vite, Tailwind CSS, daisyUI
- **Extension**: Chrome Manifest V3, Sleeper WebSocket interceptor + ESPN React Fiber scraping
