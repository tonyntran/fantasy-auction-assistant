export default function DeadMoneyAlert({ alerts }) {
  if (!alerts || alerts.length === 0) return null

  return (
    <div className="card bg-base-200 shadow-md border border-error/30">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-error">
          Dead Money Alerts
          <span className="badge badge-sm badge-error">{alerts.length}</span>
        </h2>
        <div className="max-h-32 overflow-y-auto space-y-1">
          {alerts.slice().reverse().map((a) => (
            <div key={a.player_name} className="flex items-center justify-between text-xs bg-error/10 rounded px-2 py-1">
              <span className="font-semibold truncate">{a.player_name} <span className="opacity-50">({a.position})</span></span>
              <span className="shrink-0 ml-2 font-mono">
                ${a.draft_price} <span className="opacity-50">vs ${a.fmv_at_sale}</span>
                <span className="text-error font-bold ml-1">+{a.overpay_pct}%</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
