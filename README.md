# Fantasy Auction Assistant

A real-time ESPN Fantasy Football auction draft assistant. A Chrome Extension scrapes ESPN's live draft state, a Python FastAPI backend crunches the numbers, Gemini AI provides contextual advice, and a React dashboard visualizes everything.

```
Chrome Extension ──► FastAPI Backend ──► React Dashboard
(ESPN scraping)      (VORP/FMV engine)   (live via WebSocket)
```

## Features

- **Live draft scraping** — React Fiber traversal of ESPN's draft room with DOM fallback
- **Auction math engine** — VORP, FMV, inflation tracking, positional scarcity, and roster-fit scoring
- **AI-powered advice** — Gemini 1.5 Flash with full draft context (400ms timeout, engine-only fallback)
- **BUY / PASS / PRICE_ENFORCE** recommendations with suggested bid amounts
- **Opponent modeling** — positional needs, bidding war risk, spending power analysis
- **Draft strategy profiles** — Balanced, Studs & Duds, RB Heavy, WR Heavy, Elite TE — switchable at runtime via dashboard dropdown
- **Nomination strategy** — budget drain, rival desperation, and bargain snag suggestions
- **What-if simulator** — project your roster if you win a player at a given price
- **Post-draft grading** — AI-generated letter grades per position with waiver wire targets
- **Real-time dashboard** — draft board, budget tracker, inflation chart, scarcity heatmap, live ticker

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
4. Navigate to your ESPN auction draft room — the overlay appears automatically

## Configuration

Key `.env` variables:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(none)* | Optional — runs engine-only if not set |
| `MY_TEAM_NAME` | `"My Team"` | Your team name as shown on ESPN |
| `LEAGUE_SIZE` | `10` | Number of teams |
| `BUDGET` | `200` | Starting auction budget per team |
| `ROSTER_SLOTS` | `QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF` | Roster structure |
| `DRAFT_STRATEGY` | `balanced` | Draft philosophy: `balanced`, `studs_and_duds`, `rb_heavy`, `wr_heavy`, `elite_te` |

See [OVERVIEW.md](OVERVIEW.md) for the full configuration reference, architecture details, and API documentation.

## Tech Stack

- **Backend**: Python, FastAPI, Pydantic, Google Gemini AI
- **Dashboard**: React 18, Vite, Tailwind CSS, daisyUI, Recharts
- **Extension**: Chrome Manifest V3, dual-world content scripts
