import { useEffect, useRef } from 'react'
import useDraftState, { API_BASE } from './hooks/useDraftState'
import usePersistedState from './hooks/usePersistedState'
import Header from './components/Header'
import ErrorBoundary from './components/ErrorBoundary'
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
import DraftGrade from './components/DraftGrade'
import ExportButton from './components/ExportButton'
import ManualInput from './components/ManualInput'

export default function App() {
  const { state, setState, connected, loading, refetch } = useDraftState()
  const [savedStrategy, setSavedStrategy] = usePersistedState('strategy', null)
  const restoredRef = useRef(false)

  // Restore persisted strategy on initial load
  useEffect(() => {
    if (!restoredRef.current && state && savedStrategy && state.strategy !== savedStrategy) {
      restoredRef.current = true
      fetch(`${API_BASE}/strategy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy: savedStrategy })
      }).then(() => refetch())
    }
  }, [state, savedStrategy, refetch])

  const setStrategy = async (strategy) => {
    setSavedStrategy(strategy)
    await fetch(`${API_BASE}/strategy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy })
    })
    refetch()
  }

  const setSheet = async (sheet) => {
    await fetch(`${API_BASE}/projection-sheet`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sheet })
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
      <Header state={state} connected={connected} onStrategyChange={setStrategy} onSheetChange={setSheet} />

      <main className="flex-1 p-4 overflow-auto">
        {/* Manual command input */}
        <div className="mb-4">
          <ErrorBoundary name="Manual Input">
            <ManualInput onCommandSuccess={refetch} />
          </ErrorBoundary>
        </div>

        {/* Main layout: left content columns + right optimizer sidebar */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4 items-start">
          {/* Left 3 columns */}
          <div className="lg:col-span-3 space-y-4">
            {/* Row 1: Advice + Top Remaining + Ticker */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <ErrorBoundary name="Current Advice">
                <CurrentAdvice advice={state.current_advice} positionalRun={state.positional_run} />
              </ErrorBoundary>
              <ErrorBoundary name="Top Remaining">
                <TopRemaining topRemaining={state.top_remaining} playerNews={state.player_news} positionalVona={state.positional_vona} />
              </ErrorBoundary>
              <ErrorBoundary name="Activity Feed">
                <ActivityFeed events={state.ticker_events} />
              </ErrorBoundary>
            </div>

            {/* Row 2: Team Overview + My Roster + Scarcity */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <ErrorBoundary name="My Roster">
                <MyRoster myTeam={state.my_team} />
              </ErrorBoundary>
              <ErrorBoundary name="Team Overview">
                <TeamOverview budgets={state.budgets} myTeam={state.my_team} opponentNeeds={state.opponent_needs} moneyVelocity={state.money_velocity} />
              </ErrorBoundary>
              <ErrorBoundary name="Scarcity Heat Map">
                <ScarcityHeatMap players={state.players} displayPositions={state.display_positions} />
              </ErrorBoundary>
            </div>

            {/* Row 3: VOM Leaderboard + Sleeper Watch + Nomination */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <ErrorBoundary name="VOM Leaderboard">
                <VomLeaderboard leaderboard={state.vom_leaderboard} />
              </ErrorBoundary>
              <ErrorBoundary name="Sleeper Watch">
                <SleeperWatch sleepers={state.sleepers} />
              </ErrorBoundary>
              <ErrorBoundary name="Nomination Panel">
                <NominationPanel nominations={state.nominations} />
              </ErrorBoundary>
            </div>
          </div>

          {/* Right column: Optimizer + AI Plan + Draft Grade pinned to top */}
          <div className="lg:col-span-1">
            <div className="lg:sticky lg:top-4 space-y-4">
              <ErrorBoundary name="Roster Optimizer">
                <RosterOptimizer optimizer={state.optimizer} planStaleness={state.draft_plan_staleness} />
              </ErrorBoundary>
              <ErrorBoundary name="Draft Grade">
                <DraftGrade
                  myTeam={state.my_team}
                  rosterSize={state.my_team?.roster ? Object.keys(state.my_team.roster).length : 0}
                />
              </ErrorBoundary>
              <ErrorBoundary name="Export">
                <ExportButton
                  myTeam={state.my_team}
                  rosterSize={state.my_team?.roster ? Object.keys(state.my_team.roster).length : 0}
                />
              </ErrorBoundary>
            </div>
          </div>
        </div>

        {/* Draft board: full width */}
        <ErrorBoundary name="Draft Board">
          <DraftBoard players={state.players} positions={state.positions} positionBadges={state.position_badges} playerNews={state.player_news} />
        </ErrorBoundary>

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
