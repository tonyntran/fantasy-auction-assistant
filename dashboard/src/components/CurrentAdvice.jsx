import { useState, useEffect } from 'react'

const actionStyles = {
  BUY: 'alert-success',
  PASS: 'alert-error',
  PRICE_ENFORCE: 'alert-warning',
}

export default function CurrentAdvice({ draftLog }) {
  const [advice, setAdvice] = useState(null)
  const [loading, setLoading] = useState(false)

  const latestPick = draftLog?.[draftLog.length - 1]

  useEffect(() => {
    if (!latestPick?.player) return

    setLoading(true)
    fetch(`http://localhost:8000/advice?player=${encodeURIComponent(latestPick.player)}`)
      .then(r => r.json())
      .then(data => {
        setAdvice(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [latestPick?.player])

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Current Advice</h2>

        {!advice && !loading && (
          <p className="text-xs opacity-50">Waiting for nomination...</p>
        )}

        {loading && (
          <div className="flex items-center gap-2 text-xs opacity-60">
            <span className="loading loading-spinner loading-xs" />
            Analyzing {latestPick?.player}...
          </div>
        )}

        {advice && !loading && (
          <div className={`alert ${actionStyles[advice.action] || 'alert-info'} py-3`}>
            <div className="w-full">
              <div className="flex items-center justify-between mb-1">
                <span className="text-lg font-bold">{advice.action}</span>
                <span className="text-lg font-bold">${advice.max_bid}</span>
              </div>
              <div className="flex gap-3 text-xs opacity-70 mb-1">
                <span>FMV: ${advice.fmv}</span>
                <span>Inflation: {advice.inflation_rate?.toFixed(3)}x</span>
                <span className="badge badge-xs badge-ghost">{advice.source}</span>
              </div>
              {advice.vona > 0 && (
                <div className="flex gap-2 text-xs opacity-70 mb-1">
                  <span>VONA: <b>{advice.vona}</b></span>
                  {advice.vona_next_player && <span className="opacity-60">Next: {advice.vona_next_player}</span>}
                </div>
              )}
              <p className="text-xs leading-relaxed">{advice.reasoning}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
