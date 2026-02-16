export default function OpponentNeeds({ opponentNeeds }) {
  if (!opponentNeeds || opponentNeeds.team_count === 0) {
    return (
      <div className="card bg-base-200 shadow-md">
        <div className="card-body p-4">
          <h2 className="card-title text-sm text-primary">Opponent Needs</h2>
          <p className="text-xs opacity-50">No opponent data yet.</p>
        </div>
      </div>
    )
  }

  const threats = opponentNeeds.threat_levels || []
  const rosters = opponentNeeds.team_rosters || {}
  const budgets = opponentNeeds.team_budgets || {}

  // Derive positions from all roster data, filtering out non-starter slots
  const positions = [...new Set(
    Object.values(rosters).flatMap(r => Object.keys(r))
  )].filter(p => !['BENCH', 'IR', 'UNK'].includes(p)).sort()

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">
          Opponent Needs
          <span className="badge badge-sm badge-ghost">{opponentNeeds.team_count} teams</span>
        </h2>
        <div className="overflow-x-auto">
          <table className="table table-xs">
            <thead>
              <tr>
                <th>Team</th>
                <th className="text-right">$</th>
                {positions.map(p => (
                  <th key={p} className="text-center">{p}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {threats.slice(0, 9).map((t) => (
                <tr key={t.team_id}>
                  <td>#{t.team_id}</td>
                  <td className="text-right text-success font-mono">${budgets[t.team_id] ?? '?'}</td>
                  {positions.map(pos => {
                    const count = rosters[t.team_id]?.[pos] || 0
                    return (
                      <td key={pos} className="text-center">
                        <span className={count > 0 ? '' : 'opacity-20'}>
                          {count}
                        </span>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
