function PriceChip({ pos, data }) {
  if (!data || data.count === 0) return null
  const pct = data.pct_of_fmv
  const color = pct >= 115 ? 'text-error' : pct >= 105 ? 'text-warning' : pct <= 90 ? 'text-success' : 'opacity-50'
  return (
    <span className={`text-[10px] font-mono ${color}`} title={`${pos}: ${data.count} sold at ${pct}% of FMV`}>
      {pos} {pct}%
    </span>
  )
}

export default function Header({ state, connected, onStrategyChange, onSheetChange }) {
  const budget = state?.my_team?.budget ?? '?'
  const total = state?.my_team?.total_budget ?? '?'
  const inflation = state?.inflation ?? 1
  const prices = state?.positional_prices || {}
  const run = state?.positional_run

  return (
    <div className="navbar bg-base-200 border-b border-base-300 px-6">
      <div className="navbar-start gap-3">
        <h1 className="text-lg font-bold text-primary">Fantasy Auction Dashboard</h1>
        <div className={`badge badge-xs ${connected ? 'badge-success' : 'badge-error'}`}
             title={connected ? 'Connected' : 'Disconnected'} />
      </div>
      <div className="navbar-center">
        <div className="flex items-center gap-2">
          {Object.entries(prices).map(([pos, d]) => (
            <PriceChip key={pos} pos={pos} data={d} />
          ))}
          {run && (
            <span className="badge badge-xs badge-error animate-pulse" title={`${run.consecutive} consecutive ${run.position} picks, ${run.above_fmv_count} above FMV`}>
              {run.position} RUN x{run.consecutive}
            </span>
          )}
        </div>
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
        {state?.available_sheets && state.available_sheets.length > 1 && (
          <select
            className="select select-sm select-bordered"
            value={state?.active_sheet || ''}
            onChange={(e) => onSheetChange(e.target.value)}
            title="Projection source"
          >
            {state.available_sheets.map(s => (
              <option key={s} value={s}>{s}</option>
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
