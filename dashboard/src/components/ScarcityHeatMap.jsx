import { useState } from 'react'

export default function ScarcityHeatMap({ players, displayPositions = [] }) {
  if (!players) return null

  const [expanded, setExpanded] = useState(null) // "QB" or null

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
        remaining: group.filter(p => !p.is_drafted).sort((a, b) => b.fmv - a.fmv),
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

  // Collect T1 & T2 remaining for all positions (or just expanded position)
  const elitePlayers = {}
  for (const pos of positions) {
    const t1 = grid[pos][1]?.remaining || []
    const t2 = grid[pos][2]?.remaining || []
    const combined = [...t1, ...t2]
    if (combined.length > 0) {
      elitePlayers[pos] = combined
    }
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
              <tr key={pos} className={`cursor-pointer hover:bg-base-300 ${expanded === pos ? 'bg-base-300' : ''}`}
                  onClick={() => setExpanded(expanded === pos ? null : pos)}>
                <td className="font-medium">{pos}</td>
                {tiers.map(t => {
                  const cell = grid[pos][t]
                  return (
                    <td key={t} className="text-center">
                      <span className={`badge badge-sm ${cellBadge(cell.pct)}`}
                            title={`${cell.drafted}/${cell.total} drafted — ${cell.remaining.length} left`}>
                        {cell.total > 0 ? `${cell.pct}%` : '-'}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>

        {/* T1 & T2 remaining — show expanded position or summary */}
        {expanded && elitePlayers[expanded] ? (
          <div className="mt-2 border-t border-base-300 pt-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-primary">{expanded} — Tier 1 &amp; 2 Available</span>
              <span className="text-[10px] opacity-40">{elitePlayers[expanded].length} left</span>
            </div>
            <div className="space-y-0.5 max-h-40 overflow-y-auto">
              {elitePlayers[expanded].map(p => (
                <div key={p.name} className="flex items-center justify-between text-xs px-1 py-0.5 rounded hover:bg-base-300">
                  <span className="truncate">
                    <span className="badge badge-xs badge-ghost mr-1">T{p.tier}</span>
                    {p.name}
                  </span>
                  <span className="shrink-0 ml-2 font-mono opacity-70">${p.fmv}</span>
                </div>
              ))}
            </div>
          </div>
        ) : !expanded && Object.keys(elitePlayers).length > 0 ? (
          <div className="mt-2 border-t border-base-300 pt-2">
            <span className="text-[10px] opacity-40">T1 &amp; T2 remaining:&ensp;</span>
            <div className="flex flex-wrap gap-1 mt-1">
              {positions.map(pos => {
                const count = elitePlayers[pos]?.length || 0
                if (count === 0) return null
                const t1left = grid[pos][1]?.remaining.length || 0
                const t2left = grid[pos][2]?.remaining.length || 0
                return (
                  <span key={pos}
                        className="badge badge-sm badge-outline cursor-pointer hover:badge-primary"
                        onClick={(e) => { e.stopPropagation(); setExpanded(pos) }}>
                    {pos} {t1left > 0 && <span className="text-success ml-0.5">{t1left}</span>}
                    {t1left > 0 && t2left > 0 && '/'}
                    {t2left > 0 && <span className="text-info">{t2left}</span>}
                  </span>
                )
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
