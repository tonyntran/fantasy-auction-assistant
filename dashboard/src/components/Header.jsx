export default function Header({ state, connected }) {
  const budget = state?.my_team?.budget ?? '?'
  const total = state?.my_team?.total_budget ?? '?'
  const inflation = state?.inflation ?? 1

  return (
    <div className="navbar bg-base-200 border-b border-base-300 px-6">
      <div className="navbar-start gap-3">
        <h1 className="text-lg font-bold text-primary">Fantasy Auction Dashboard</h1>
        <div className={`badge badge-xs ${connected ? 'badge-success' : 'badge-error'}`}
             title={connected ? 'Connected' : 'Disconnected'} />
      </div>
      <div className="navbar-end gap-4 text-sm">
        <div className="flex items-center gap-1">
          <span className="opacity-60">Budget:</span>
          <span className="font-bold">${budget}</span>
          <span className="opacity-40">/ ${total}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="opacity-60">Inflation:</span>
          <span className="font-bold">{Number(inflation).toFixed(3)}x</span>
        </div>
        <div className="badge badge-primary badge-outline">
          {state?.draft_log?.length ?? 0} drafted
        </div>
      </div>
    </div>
  )
}
