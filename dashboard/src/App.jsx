import useDraftState from './hooks/useDraftState'
import Header from './components/Header'
import CurrentAdvice from './components/CurrentAdvice'
import MyRoster from './components/MyRoster'
import DraftBoard from './components/DraftBoard'
import BudgetTracker from './components/BudgetTracker'
import InflationGraph from './components/InflationGraph'
import ScarcityHeatMap from './components/ScarcityHeatMap'
import TopRemaining from './components/TopRemaining'
import SleeperWatch from './components/SleeperWatch'
import NominationPanel from './components/NominationPanel'
import OpponentNeeds from './components/OpponentNeeds'
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
        {/* Dead money banner — conditional */}
        {state.dead_money_alerts?.length > 0 && (
          <div className="mb-4">
            <DeadMoneyAlert alerts={state.dead_money_alerts} />
          </div>
        )}

        {/* Top row: Advice + Roster + Top Remaining + Ticker */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4">
          <CurrentAdvice draftLog={state.draft_log} />
          <MyRoster roster={state.my_team?.roster} players={state.my_team?.players_acquired} />
          <TopRemaining topRemaining={state.top_remaining} />
          <ActivityFeed events={state.ticker_events} />
        </div>

        {/* Middle row: Charts */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <BudgetTracker budgets={state.budgets} myTeam={state.my_team} />
          <InflationGraph history={state.inflation_history} />
          <ScarcityHeatMap players={state.players} displayPositions={state.display_positions} />
          <NominationPanel nominations={state.nominations} />
        </div>

        {/* Bottom row: Full-width tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          <SleeperWatch sleepers={state.sleepers} />
          <OpponentNeeds opponentNeeds={state.opponent_needs} />
        </div>

        {/* Draft board: full width */}
        <DraftBoard players={state.players} positions={state.positions} positionBadges={state.position_badges} />
      </main>
    </div>
  )
}
