import useDraftState, { API_BASE } from './hooks/useDraftState'
import Header from './components/Header'
import CurrentAdvice from './components/CurrentAdvice'
import MyRoster from './components/MyRoster'
import DraftBoard from './components/DraftBoard'
import TeamOverview from './components/TeamOverview'
import ScarcityHeatMap from './components/ScarcityHeatMap'
import TopRemaining from './components/TopRemaining'
import SleeperWatch from './components/SleeperWatch'
import NominationPanel from './components/NominationPanel'
import ActivityFeed from './components/ActivityFeed'

import VomLeaderboard from './components/VomLeaderboard'
import RosterOptimizer from './components/RosterOptimizer'

export default function App() {
  const { state, setState, connected, loading, refetch } = useDraftState()

  const setStrategy = async (strategy) => {
    await fetch(`${API_BASE}/strategy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy })
    })
    refetch()
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span className="loading loading-spinner loading-lg text-primary" />
      </div>
    )
  }

  if (!state) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="alert alert-error max-w-sm">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-5 w-5" fill="none" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <div>
            <h3 className="font-bold text-sm">Cannot reach server</h3>
            <p className="text-xs">Make sure the backend is running on localhost:8000</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header state={state} connected={connected} onStrategyChange={setStrategy} />

      <main className="flex-1 p-4 overflow-auto">
        {/* Main layout: left content columns + right optimizer sidebar */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4 items-start">
          {/* Left 3 columns */}
          <div className="lg:col-span-3 space-y-4">
            {/* Row 1: Advice + Top Remaining + Ticker */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <CurrentAdvice advice={state.current_advice} />
              <TopRemaining topRemaining={state.top_remaining} />
              <ActivityFeed events={state.ticker_events} />
            </div>

            {/* Row 2: Team Overview + My Roster + Scarcity */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <MyRoster myTeam={state.my_team} />
              <TeamOverview budgets={state.budgets} myTeam={state.my_team} opponentNeeds={state.opponent_needs} />
              <ScarcityHeatMap players={state.players} displayPositions={state.display_positions} />
            </div>

            {/* Row 3: VOM Leaderboard + Sleeper Watch + Nomination */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <VomLeaderboard leaderboard={state.vom_leaderboard} />
              <SleeperWatch sleepers={state.sleepers} />
              <NominationPanel nominations={state.nominations} />
            </div>
          </div>

          {/* Right column: Optimizer + AI Plan pinned to top */}
          <div className="lg:col-span-1">
            <div className="lg:sticky lg:top-4">
              <RosterOptimizer optimizer={state.optimizer} planStaleness={state.draft_plan_staleness} />
            </div>
          </div>
        </div>

        {/* Draft board: full width */}
        <DraftBoard players={state.players} positions={state.positions} positionBadges={state.position_badges} playerNews={state.player_news} />

        {/* Glossary */}
        <div className="card bg-base-200 shadow-md mt-4">
          <div className="card-body p-4">
            <h2 className="card-title text-sm text-primary">Glossary</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-2 text-xs opacity-70">
              <div>
                <span className="font-semibold text-base-content">VORP</span> — Value Over Replacement Player. How many more fantasy points a player projects over the best freely available player at their position.
                <div className="mt-0.5 opacity-60">
                  <span className="text-success">10+</span> = elite starter&ensp;
                  <span className="text-info">5–10</span> = solid starter&ensp;
                  <span className="text-warning">1–5</span> = fringe&ensp;
                  <span className="text-error">0</span> = replacement level
                </div>
              </div>
              <div>
                <span className="font-semibold text-base-content">VONA</span> — Value Over Next Available. The drop-off in projected points between this player and the next-best undrafted player at the same position. A high VONA means there's a big gap — don't let this player slip.
                <div className="mt-0.5 opacity-60">
                  <span className="text-success">5+</span> = must-buy tier drop&ensp;
                  <span className="text-info">2–5</span> = notable gap&ensp;
                  <span className="text-warning">0–2</span> = similar options exist
                </div>
              </div>
              <div>
                <span className="font-semibold text-base-content">FMV</span> — Fair Market Value. The inflation-adjusted auction price based on a player's baseline value and current league spending. Compare to the live bid to decide if a player is a bargain or overpay.
              </div>
              <div>
                <span className="font-semibold text-base-content">Inflation</span> — Ratio of remaining league cash to remaining player value. Above 1.0 means more cash than value left (prices will rise); below 1.0 means bargains are likely.
              </div>
              <div>
                <span className="font-semibold text-base-content">VOM</span> — Value Over Market. Difference between a player's FMV and what they actually sold for. Positive = bargain, negative = overpay.
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
