export default function SleeperWatch({ sleepers }) {
  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Sleeper Watch</h2>

        {(!sleepers || sleepers.length === 0) ? (
          <p className="text-xs opacity-50">No sleeper candidates yet.</p>
        ) : (
          <div className="space-y-1.5 max-h-64 overflow-y-auto">
            {sleepers.map((s, i) => (
              <div key={i} className="flex items-center justify-between text-xs bg-base-300 rounded-lg px-3 py-2">
                <div className="flex-1 min-w-0">
                  <span className="font-medium">{s.player_name}</span>
                  <span className="badge badge-xs badge-ghost ml-1">{s.position}</span>
                  {s.tier && <span className="opacity-40 ml-1">T{s.tier}</span>}
                </div>
                <div className="flex gap-3 text-right whitespace-nowrap">
                  <span className="opacity-50">VORP {s.vorp}</span>
                  <span className="text-success font-mono">${s.fmv}</span>
                  <span className="badge badge-sm badge-warning">{s.sleeper_score?.toFixed(1)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
