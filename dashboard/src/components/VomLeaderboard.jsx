export default function VomLeaderboard({ leaderboard }) {
  if (!leaderboard || leaderboard.length === 0) {
    return (
      <div className="card bg-base-200 shadow-md">
        <div className="card-body p-4">
          <h2 className="card-title text-sm text-primary">Value Over Market</h2>
          <p className="text-xs opacity-50">No drafted players yet.</p>
        </div>
      </div>
    )
  }

  // Show top 5 bargains and top 5 overpays
  const bargains = leaderboard.filter(p => p.vom > 0).slice(0, 5)
  const overpays = [...leaderboard].filter(p => p.vom < 0).sort((a, b) => a.vom - b.vom).slice(0, 5)

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Value Over Market</h2>
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {bargains.length > 0 && (
            <>
              <div className="text-[10px] uppercase tracking-wider opacity-40 font-semibold mt-1">Bargains</div>
              {bargains.map(p => (
                <div key={p.player_name} className="flex items-center justify-between text-xs bg-base-300 rounded-lg px-3 py-1.5">
                  <div className="flex-1 min-w-0">
                    <span className="font-medium truncate">{p.player_name}</span>
                    <span className="badge badge-xs badge-ghost ml-1">{p.position}</span>
                  </div>
                  <div className="flex gap-2 text-right whitespace-nowrap">
                    <span className="opacity-40">${p.draft_price}</span>
                    <span className="opacity-50">FMV ${p.fmv}</span>
                    <span className="text-success font-semibold font-mono">+{p.vom}</span>
                    {p.par_dollar != null && <span className="opacity-40" title="Points Above Replacement per $">{p.par_dollar}/$ </span>}
                  </div>
                </div>
              ))}
            </>
          )}
          {overpays.length > 0 && (
            <>
              <div className="text-[10px] uppercase tracking-wider opacity-40 font-semibold mt-2">Overpays</div>
              {overpays.map(p => (
                <div key={p.player_name} className="flex items-center justify-between text-xs bg-base-300 rounded-lg px-3 py-1.5">
                  <div className="flex-1 min-w-0">
                    <span className="font-medium truncate">{p.player_name}</span>
                    <span className="badge badge-xs badge-ghost ml-1">{p.position}</span>
                  </div>
                  <div className="flex gap-2 text-right whitespace-nowrap">
                    <span className="opacity-40">${p.draft_price}</span>
                    <span className="opacity-50">FMV ${p.fmv}</span>
                    <span className="text-error font-semibold font-mono">{p.vom}</span>
                    {p.par_dollar != null && <span className="opacity-40" title="Points Above Replacement per $">{p.par_dollar}/$</span>}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
