export default function MyRoster({ myTeam }) {
  if (!myTeam) return null
  const { roster, slot_types, budget, total_budget, players_acquired } = myTeam
  const totalSpent = players_acquired?.reduce((s, p) => s + p.price, 0) ?? 0

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

  const renderSlot = ([slot, player]) => {
    const base = slot_types?.[slot] || slot.replace(/\d+$/, '')
    const label = base === 'BENCH' ? 'BN' : slot
    return (
      <div key={slot} className="flex justify-between">
        <span className="opacity-50 w-16">{label}</span>
        <span className={`flex-1 ${player ? 'font-medium' : 'opacity-30'}`}>
          {player || '—'}
        </span>
        {player && players_acquired && (() => {
          const pick = players_acquired.find(p => p.name === player)
          return pick ? <span className="opacity-50">${pick.price}</span> : null
        })()}
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
          <span>Remaining: <b className="text-base-content">${budget}</b></span>
        </div>
      </div>
    </div>
  )
}
