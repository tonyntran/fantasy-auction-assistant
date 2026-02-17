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
          <>
            {/* Action badge + key numbers */}
            <div className={`alert ${actionStyles[advice.action] || 'alert-info'} py-3`}>
              <div className="w-full">
                <div className="flex items-center justify-between mb-1">
                  <div>
                    <span className="text-lg font-bold">{advice.action}</span>
                    <span className="text-sm opacity-70 ml-2">{advice.player}</span>
                  </div>
                  <span className="text-lg font-bold">${advice.max_bid ?? '?'}</span>
                </div>
                <div className="flex flex-wrap gap-3 text-xs opacity-70">
                  <span>FMV: ${advice.fmv ?? '?'}</span>
                  <span>Bid: ${advice.current_bid ?? '?'}</span>
                  {advice.high_bidder && <span>By: {advice.high_bidder}</span>}
                  {advice.vorp != null && <span>VORP: {advice.vorp}</span>}
                  {advice.vona > 0 && <span>VONA: {advice.vona}</span>}
                  {advice.scarcity_multiplier != null && advice.scarcity_multiplier !== 1.0 && (
                    <span>Scarcity: {advice.scarcity_multiplier}x</span>
                  )}
                </div>
              </div>
            </div>

            {/* Player news badge */}
            {advice.player_news && (
              <div className="flex items-center gap-2 mt-1 text-xs">
                <span className="badge badge-xs badge-warning">Injury</span>
                <span className="opacity-70">
                  {advice.player_news.status}
                  {advice.player_news.injury && ` (${advice.player_news.injury})`}
                  {advice.player_news.injury_note && ` — ${advice.player_news.injury_note}`}
                </span>
              </div>
            )}

            {/* Engine reasoning (always shown, compact) */}
            {advice.engine_reasoning && (
              <div className="text-xs opacity-60 mt-2">
                <span className="badge badge-xs badge-ghost mr-1">Engine</span>
                {advice.engine_reasoning}
              </div>
            )}

            {/* AI reasoning (only when AI advice is available, formatted nicely) */}
            {advice.source === 'ai' && advice.ai_reasoning && (
              <div className="mt-2 p-3 bg-base-300 rounded-lg">
                <span className="badge badge-xs badge-accent mb-1">AI Analysis</span>
                <p className="text-sm leading-relaxed">{advice.ai_reasoning}</p>
              </div>
            )}

            {/* VONA context */}
            {advice.vona > 0 && advice.vona_next_player && (
              <div className="text-[11px] opacity-40 mt-1">
                Next at position: {advice.vona_next_player} ({advice.vona} pts drop)
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
