const actionStyles = {
  BUY: 'alert-success',
  PASS: 'alert-error',
  PRICE_ENFORCE: 'alert-warning',
}

export default function CurrentAdvice({ advice }) {
  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Current Advice</h2>

        {!advice && (
          <p className="text-xs opacity-50">Waiting for nomination...</p>
        )}

        {advice && (
          <div className={`alert ${actionStyles[advice.action] || 'alert-info'} py-3`}>
            <div className="w-full">
              <div className="flex items-center justify-between mb-1">
                <div>
                  <span className="text-lg font-bold">{advice.action}</span>
                  <span className="text-sm opacity-70 ml-2">{advice.player}</span>
                </div>
                <span className="text-lg font-bold">${advice.max_bid ?? '?'}</span>
              </div>
              <div className="flex gap-3 text-xs opacity-70 mb-1">
                <span>FMV: ${advice.fmv ?? '?'}</span>
                <span>Bid: ${advice.current_bid ?? '?'}</span>
                {advice.high_bidder && <span>By: {advice.high_bidder}</span>}
                <span>Inflation: {advice.inflation_rate?.toFixed(3)}x</span>
                <span className={`badge badge-xs ${advice.source === 'ai' ? 'badge-accent' : 'badge-ghost'}`}>{advice.source === 'ai' ? 'AI' : 'engine'}</span>
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
