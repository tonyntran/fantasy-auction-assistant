import useDraftState from './hooks/useDraftState'
import Header from './components/Header'
import CurrentAdvice from './components/CurrentAdvice'
import MyRoster from './components/MyRoster'
import DraftBoard from './components/DraftBoard'
import TeamOverview from './components/TeamOverview'
import InflationGraph from './components/InflationGraph'
import ScarcityHeatMap from './components/ScarcityHeatMap'
import TopRemaining from './components/TopRemaining'
import SleeperWatch from './components/SleeperWatch'
import NominationPanel from './components/NominationPanel'
import ActivityFeed from './components/ActivityFeed'
import DeadMoneyAlert from './components/DeadMoneyAlert'

export default function App() {
  const { state, connected, loading } = useDraftState()

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
      <Header state={state} connected={connected} />

      <main className="flex-1 p-4 overflow-auto">
        {/* Top row: Advice + Roster + Top Remaining + Ticker + Dead Money */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-4">
          <CurrentAdvice advice={state.current_advice} />
          <MyRoster myTeam={state.my_team} />
          <TopRemaining topRemaining={state.top_remaining} />
          <ActivityFeed events={state.ticker_events} />
          <DeadMoneyAlert alerts={state.dead_money_alerts} />
        </div>

        {/* Middle row: Unified Team Budgets & Needs + Scarcity */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
          <div className="lg:col-span-2">
            <TeamOverview budgets={state.budgets} myTeam={state.my_team} opponentNeeds={state.opponent_needs} />
          </div>
          <ScarcityHeatMap players={state.players} displayPositions={state.display_positions} />
        </div>

        {/* Next row: Sleeper Watch + Nomination + Inflation */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
          <SleeperWatch sleepers={state.sleepers} />
          <NominationPanel nominations={state.nominations} />
          <InflationGraph history={state.inflation_history} />
        </div>

        {/* Draft board: full width */}
        <DraftBoard players={state.players} positions={state.positions} positionBadges={state.position_badges} />

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
                <span className="font-semibold text-base-content">Dead Money</span> — Overpay amount when a player sells above FMV. This cash is "lost" from the league pool, increasing inflation for remaining players.
              </div>
              <div>
                <span className="font-semibold text-base-content">Tier</span> — Players grouped by projected output. A tier break between two players means a meaningful drop in expected production.
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
