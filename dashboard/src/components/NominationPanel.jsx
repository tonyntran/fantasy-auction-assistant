const strategyBadges = {
  BUDGET_DRAIN: 'badge-error',
  RIVAL_DESPERATION: 'badge-warning',
  BARGAIN_SNAG: 'badge-success',
}

const strategyLabels = {
  BUDGET_DRAIN: 'Drain',
  RIVAL_DESPERATION: 'Desperation',
  BARGAIN_SNAG: 'Bargain',
}

export default function NominationPanel({ nominations }) {
  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Nomination Strategy</h2>

        {(!nominations || nominations.length === 0) ? (
          <p className="text-xs opacity-50">No suggestions available.</p>
        ) : (
          <div className="space-y-2">
            {nominations.map((n) => (
              <div key={`${n.player_name}-${n.strategy}`} className="bg-base-300 rounded-lg px-3 py-2">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold">{n.player_name}</span>
                    <span className="badge badge-xs badge-ghost">{n.position}</span>
                  </div>
                  <span className={`badge badge-sm ${strategyBadges[n.strategy] || 'badge-ghost'}`}>
                    {strategyLabels[n.strategy] || n.strategy}
                  </span>
                </div>
                <p className="text-xs opacity-60">{n.reasoning}</p>
                <div className="flex gap-3 mt-1 text-xs opacity-40">
                  <span>FMV ${n.fmv}</span>
                  <span>Priority {n.priority}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
