import { useRef, useEffect } from 'react'

const METRICS = [
  { key: 'position', label: 'Position', type: 'text' },
  { key: 'tier', label: 'Tier', type: 'lowest' },
  { key: 'projected_points', label: 'Projected Pts', type: 'highest' },
  { key: 'fmv', label: 'FMV', type: 'display', format: v => `$${v}` },
  { key: 'vorp', label: 'VORP', type: 'highest' },
  { key: 'vona', label: 'VONA', type: 'highest' },
  { key: 'baseline_aav', label: 'AAV', type: 'display', format: v => `$${v}` },
]

function bestIndex(players, key, direction) {
  let bestIdx = 0
  let bestVal = players[0][key] ?? 0
  for (let i = 1; i < players.length; i++) {
    const val = players[i][key] ?? 0
    if (direction === 'highest' ? val > bestVal : val < bestVal) {
      bestVal = val
      bestIdx = i
    }
  }
  // Only highlight if there is a meaningful difference (not all identical)
  const allSame = players.every(p => (p[key] ?? 0) === bestVal)
  return allSame ? -1 : bestIdx
}

function formatValue(metric, value) {
  if (value == null) return '-'
  if (metric.format) return metric.format(value)
  if (typeof value === 'number') return value
  return value
}

export default function PlayerComparison({ players, onClose }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog) {
      dialog.showModal()
    }
  }, [])

  if (!players || players.length < 2) return null

  return (
    <dialog ref={dialogRef} className="modal" onClose={onClose}>
      <div className="modal-box max-w-xl">
        <h3 className="font-bold text-lg mb-4">Player Comparison</h3>

        <div className="overflow-x-auto">
          <table className="table table-sm table-zebra">
            <thead>
              <tr>
                <th className="text-xs">Metric</th>
                {players.map(p => (
                  <th key={p.name} className="text-center text-xs">{p.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRICS.map(metric => {
                const winner = (metric.type === 'highest' || metric.type === 'lowest')
                  ? bestIndex(players, metric.key, metric.type)
                  : -1

                return (
                  <tr key={metric.key}>
                    <td className="font-medium text-xs opacity-70">{metric.label}</td>
                    {players.map((p, idx) => (
                      <td
                        key={p.name}
                        className={`text-center font-mono text-sm ${idx === winner ? 'font-bold text-success' : ''}`}
                      >
                        {formatValue(metric, p[metric.key])}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="modal-action">
          <form method="dialog">
            <button className="btn btn-sm">Close</button>
          </form>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  )
}
