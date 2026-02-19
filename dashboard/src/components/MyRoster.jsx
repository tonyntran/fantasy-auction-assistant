const SEASON_GAMES = 17

export default function MyRoster({ myTeam }) {
  if (!myTeam) return null
  const { roster, slot_types, budget, total_budget, players_acquired } = myTeam
  const totalSpent = players_acquired?.reduce((s, p) => s + p.price, 0) ?? 0

  // Build lookup from players_acquired
  const pickMap = {}
  for (const p of (players_acquired || [])) {
    pickMap[p.name] = p
  }

  // Split roster into starters and bench
  const entries = Object.entries(roster || {})
  const starters = entries.filter(([slot]) => {
    const base = slot_types?.[slot] || slot.replace(/\d+$/, '')
    return base !== 'BENCH'
  })
  const bench = entries.filter(([slot]) => {
    const base = slot_types?.[slot] || slot.replace(/\d+$/, '')
    return base === 'BENCH'
  })

  // Totals for starters only
  const starterPicks = starters
    .map(([, player]) => player && pickMap[player])
    .filter(Boolean)
  const totalStarterPts = starterPicks.reduce((s, p) => s + (p.projected_points || 0), 0)
  const totalWeeklyPts = totalStarterPts / SEASON_GAMES

  const renderSlot = ([slot, player]) => {
    const base = slot_types?.[slot] || slot.replace(/\d+$/, '')
    const label = base === 'BENCH' ? 'BN' : slot
    const pick = player ? pickMap[player] : null
    const weeklyPts = pick?.projected_points ? (pick.projected_points / SEASON_GAMES).toFixed(1) : null
    const ptsDollar = pick?.projected_points && pick.price > 0
      ? (pick.projected_points / pick.price).toFixed(1)
      : null

    return (
      <div key={slot} className="flex items-center justify-between">
        <span className="opacity-50 w-12">{label}</span>
        <span className={`flex-1 ${player ? 'font-medium' : 'opacity-30'}`}>
          {player || '—'}
        </span>
        {pick && (
          <div className="flex gap-2 text-right whitespace-nowrap">
            <span className="opacity-40 w-12">{weeklyPts}/wk</span>
            <span className="opacity-30 w-12">{ptsDollar}/$</span>
            <span className="opacity-50 w-8 text-right">${pick.price}</span>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">My Roster</h2>
        <div className="space-y-1 text-xs">
          {starters.map(renderSlot)}
          {bench.length > 0 && (
            <>
              <div className="divider my-0.5 text-[10px] opacity-40">BENCH</div>
              {bench.map(renderSlot)}
            </>
          )}
        </div>
        <div className="divider my-1" />
        <div className="flex justify-between text-xs opacity-60">
          <span>Spent: ${totalSpent}</span>
          {starterPicks.length > 0 && (
            <span className="font-semibold text-base-content">{totalWeeklyPts.toFixed(1)} pts/wk</span>
          )}
          <span>Remaining: <b className="text-base-content">${budget}</b></span>
        </div>
      </div>
    </div>
  )
}
