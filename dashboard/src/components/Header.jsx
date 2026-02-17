export default function Header({ state, connected, onStrategyChange }) {
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
        {state?.strategies && (
          <select
            className="select select-sm select-bordered"
            value={state?.strategy || 'balanced'}
            onChange={(e) => onStrategyChange(e.target.value)}
            title={state?.strategies?.[state?.strategy]?.description || ''}
          >
            {Object.entries(state.strategies).map(([key, s]) => (
              <option key={key} value={key}>{s.label}</option>
            ))}
          </select>
        )}
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
        {state?.ai_status && (
          <div className={`badge badge-sm ${
            state.ai_status === 'ok' ? 'badge-success' :
            state.ai_status === 'idle' ? 'badge-ghost' :
            state.ai_status === 'no_key' ? 'badge-ghost' :
            state.ai_status.startsWith('rate_limited') ? 'badge-warning' :
            'badge-error'
          }`} title={`AI: ${state.ai_status}`}>
            AI: {state.ai_status}
          </div>
        )}
      </div>
    </div>
  )
}
