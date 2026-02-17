export default function RosterOptimizer({ optimizer }) {
  if (!optimizer || !optimizer.optimal_picks || optimizer.optimal_picks.length === 0) {
    return (
      <div className="card bg-base-200 shadow-md">
        <div className="card-body p-4">
          <h2 className="card-title text-sm text-primary">Optimal Remaining Picks</h2>
          <p className="text-xs opacity-50">Roster is full or no picks available.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <div className="flex items-center justify-between mb-1">
          <h2 className="card-title text-sm text-primary">Optimal Remaining Picks</h2>
          {optimizer.slots_to_fill > 0 && (
            <span className="badge badge-sm badge-info">{optimizer.slots_to_fill} slots</span>
          )}
        </div>
        <div className="space-y-1 max-h-56 overflow-y-auto">
          {optimizer.optimal_picks.map((p, i) => (
            <div key={p.player} className="flex items-center justify-between text-xs bg-base-300 rounded-lg px-3 py-1.5">
              <div className="flex-1 min-w-0">
                <span className="opacity-40 mr-1">{i + 1}.</span>
                <span className="font-medium">{p.player}</span>
                <span className="badge badge-xs badge-ghost ml-1">{p.position}</span>
                {p.tier && <span className="opacity-40 ml-1">T{p.tier}</span>}
              </div>
              <div className="flex gap-2 text-right whitespace-nowrap">
                <span className="opacity-50">VORP {p.vorp}</span>
                <span className="text-success font-mono">~${p.estimated_price}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-between text-[11px] opacity-50 mt-2 pt-2 border-t border-base-300">
          <span>Est. cost: ${optimizer.total_estimated_cost}</span>
          <span>+{optimizer.projected_points_added} pts</span>
          <span>${optimizer.remaining_budget_after} left</span>
        </div>
      </div>
    </div>
  )
}
