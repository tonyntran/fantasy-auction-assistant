export default function DeadMoneyAlert({ alerts }) {
  if (!alerts || alerts.length === 0) return null

  return (
    <div className="card bg-base-200 shadow-md border border-error/30">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-error">Dead Money Alerts</h2>
        <div className="space-y-2">
          {alerts.map((a, i) => (
            <div key={i} className="alert alert-error py-2 px-3">
              <div className="text-xs">
                <div className="font-bold">
                  {a.player_name} ({a.position}) — {a.team}
                </div>
                <div className="opacity-80">
                  Paid <span className="font-mono font-bold">${a.draft_price}</span> vs
                  FMV <span className="font-mono">${a.fmv_at_sale}</span>
                  {' '}— <span className="font-bold">+{a.overpay_pct}% overpay</span>
                </div>
                {a.inflation_change !== 0 && (
                  <div className="opacity-60 mt-0.5">
                    Inflation: {a.pre_inflation}x → {a.new_inflation}x
                    ({a.inflation_change > 0 ? '+' : ''}{a.inflation_change})
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
