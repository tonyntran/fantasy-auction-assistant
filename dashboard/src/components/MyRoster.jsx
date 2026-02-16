export default function MyRoster({ myTeam }) {
  if (!myTeam) return null
  const { roster, budget, total_budget, players_acquired } = myTeam
  const totalSpent = players_acquired?.reduce((s, p) => s + p.price, 0) ?? 0

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">My Roster</h2>
        <div className="space-y-1 text-xs">
          {roster && Object.entries(roster).map(([slot, player]) => (
            <div key={slot} className="flex justify-between">
              <span className="opacity-50 w-16">{slot}</span>
              <span className={`flex-1 ${player ? 'font-medium' : 'opacity-30'}`}>
                {player || '—'}
              </span>
              {player && players_acquired && (() => {
                const pick = players_acquired.find(p => p.name === player)
                return pick ? <span className="opacity-50">${pick.price}</span> : null
              })()}
            </div>
          ))}
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
