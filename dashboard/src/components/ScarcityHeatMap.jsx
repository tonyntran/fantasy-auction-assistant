export default function ScarcityHeatMap({ players, displayPositions = [] }) {
  if (!players) return null

  // Derive positions from data if not provided
  const positions = displayPositions.length > 0
    ? displayPositions
    : [...new Set(players.map(p => p.position))].filter(p => !['K', 'DEF', 'BENCH', 'IR'].includes(p))
  const tiers = [1, 2, 3, 4, 5]

  const grid = {}
  for (const pos of positions) {
    grid[pos] = {}
    for (const tier of tiers) {
      const group = players.filter(p => p.position === pos && p.tier === tier)
      const drafted = group.filter(p => p.is_drafted).length
      const total = group.length
      grid[pos][tier] = {
        total,
        drafted,
        pct: total > 0 ? Math.round((drafted / total) * 100) : 0,
      }
    }
  }

  function cellBadge(pct) {
    if (pct >= 85) return 'badge-error'
    if (pct >= 70) return 'badge-warning'
    if (pct >= 50) return 'badge-info'
    if (pct > 0) return 'badge-ghost'
    return 'badge-ghost opacity-30'
  }

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Position Scarcity</h2>
        <table className="table table-xs">
          <thead>
            <tr>
              <th>Pos</th>
              {tiers.map(t => <th key={t} className="text-center">T{t}</th>)}
            </tr>
          </thead>
          <tbody>
            {positions.map(pos => (
              <tr key={pos}>
                <td className="font-medium">{pos}</td>
                {tiers.map(t => {
                  const cell = grid[pos][t]
                  return (
                    <td key={t} className="text-center">
                      <span className={`badge badge-sm ${cellBadge(cell.pct)}`}
                            title={`${cell.drafted}/${cell.total} drafted`}>
                        {cell.total > 0 ? `${cell.pct}%` : '-'}
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
  )
}
