export default function BudgetTracker({ budgets }) {
  if (!budgets || Object.keys(budgets).length === 0) return null

  const data = Object.entries(budgets).map(([team, budget]) => ({
    team: team.length > 12 ? team.slice(0, 12) + '...' : team,
    budget,
  })).sort((a, b) => b.budget - a.budget)

  const maxBudget = 200

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Team Budgets</h2>
        <div className="space-y-1.5">
          {data.map(d => (
            <div key={d.team} className="flex items-center gap-2 text-xs">
              <span className="opacity-50 w-24 truncate">{d.team}</span>
              <progress
                className="progress progress-primary flex-1 h-3"
                value={d.budget}
                max={maxBudget}
              />
              <span className="font-mono w-8 text-right">${d.budget}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
