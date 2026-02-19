const actionStyles = {
  BUY: 'alert-success',
  PASS: 'alert-error',
  PRICE_ENFORCE: 'alert-warning',
}

function getVerdict(advice) {
  const { action, current_bid, fmv, max_bid } = advice
  if (!fmv || fmv <= 0) return null

  const bid = current_bid ?? 0
  const diffPct = Math.round(Math.abs(bid - fmv) / fmv * 100)
  const below = bid <= fmv

  if (action === 'PRICE_ENFORCE') {
    return `$${bid} is ${diffPct}% below market FMV $${fmv} — bid up to $${max_bid} to deny the bargain`
  }
  if (action === 'BUY' && bid <= 0) {
    return `FMV $${fmv} — bid up to $${max_bid}`
  }
  if (action === 'BUY' && below) {
    return `$${bid} is ${diffPct}% below FMV $${fmv} — good value up to $${max_bid}`
  }
  if (action === 'BUY' && !below) {
    return `$${bid} is ${diffPct}% above FMV $${fmv} — over value, max $${max_bid} if you need the position`
  }
  if (action === 'PASS' && bid > 0 && fmv > 0) {
    return below
      ? `Low value player — not worth pursuing`
      : `$${bid} is ${diffPct}% above FMV $${fmv} — let them overpay`
  }
  return null
}

function getContextTags(advice) {
  const tags = []
  const { scarcity_multiplier, strategy_multiplier, adp_vs_fmv, opponent_demand, player_news } = advice

  if (player_news) {
    const label = player_news.status + (player_news.injury ? ` (${player_news.injury})` : '')
    tags.push({ label, style: 'badge-warning' })
  }
  if (scarcity_multiplier != null && scarcity_multiplier > 1.0) {
    tags.push({ label: `Scarcity ${scarcity_multiplier}x`, style: 'badge-error' })
  }
  if (strategy_multiplier != null && strategy_multiplier !== 1.0) {
    tags.push({ label: `Strategy ${strategy_multiplier}x`, style: 'badge-info' })
  }
  if (adp_vs_fmv) {
    tags.push({ label: adp_vs_fmv, style: 'badge-ghost' })
  }
  if (opponent_demand && opponent_demand.bidding_war_risk) {
    tags.push({ label: `${opponent_demand.teams_needing} teams need pos`, style: 'badge-error' })
  }
  return tags
}

export default function CurrentAdvice({ advice }) {
  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Current Advice</h2>

        {!advice && (
          <p className="text-xs opacity-50">Waiting for nomination...</p>
        )}

        {advice && (() => {
          const verdict = getVerdict(advice)
          const tags = getContextTags(advice)
          return (
            <>
              {/* 1. Action + player + max bid */}
              <div className={`alert ${actionStyles[advice.action] || 'alert-info'} py-3`}>
                <div className="w-full">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-lg font-bold">{advice.action}</span>
                      <span className="text-sm opacity-70 ml-2">{advice.player}</span>
                    </div>
                    <div className="text-right">
                      <span className="text-lg font-bold">${advice.max_bid ?? '?'}</span>
                      {advice.current_bid > 0 && (
                        <div className="text-xs opacity-60">
                          bid: ${advice.current_bid}{advice.high_bidder && ` by ${advice.high_bidder}`}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 2. Verdict line */}
                  {verdict && (
                    <div className="text-xs mt-1 opacity-80 font-medium">{verdict}</div>
                  )}
                </div>
              </div>

              {/* 3. Stat grid */}
              <div className="grid grid-cols-3 gap-2 mt-2 text-center">
                <StatCell label="FMV" value={`$${advice.fmv ?? '?'}`} />
                <StatCell label="VORP" value={advice.vorp ?? '?'} />
                <StatCell label="VONA" value={advice.vona > 0 ? advice.vona : '—'} sub={advice.vona > 0 && advice.vona_next_player ? `vs ${advice.vona_next_player}` : null} />
                <StatCell label="Inflation" value={advice.inflation_rate ? `${advice.inflation_rate}x` : '?'} />
                <StatCell label="Scarcity" value={advice.scarcity_multiplier ? `${advice.scarcity_multiplier}x` : '1.0x'} />
                <StatCell label="Max Afford" value={`$${advice.max_bid ?? '?'}`} />
              </div>

              {/* 4. Context tags */}
              {tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {tags.map((t, i) => (
                    <span key={i} className={`badge badge-sm ${t.style}`}>{t.label}</span>
                  ))}
                </div>
              )}

              {/* 5. AI take — fixed-height slot to prevent layout shift */}
              <div className="mt-2 p-2 bg-base-300 rounded-lg min-h-20">
                {advice.source === 'ai' && advice.ai_reasoning ? (
                  <>
                    <span className="badge badge-xs badge-accent">AI</span>
                    <p className="text-xs mt-1 leading-relaxed opacity-80">{advice.ai_reasoning}</p>
                  </>
                ) : (
                  <div className="flex items-center justify-center h-full">
                    <span className="text-xs opacity-30">AI analysis pending...</span>
                  </div>
                )}
              </div>
            </>
          )
        })()}
      </div>
    </div>
  )
}

function StatCell({ label, value, sub }) {
  return (
    <div className="bg-base-300 rounded px-2 py-1">
      <div className="text-[10px] uppercase opacity-40">{label}</div>
      <div className="text-sm font-semibold">{value}</div>
      {sub && <div className="text-[10px] opacity-40 truncate">{sub}</div>}
    </div>
  )
}
