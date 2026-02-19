import { useState } from 'react'
import { API_BASE } from '../hooks/useDraftState'

function StalenessBadge({ picksSince }) {
  if (picksSince === null || picksSince === undefined) return null
  if (picksSince === 0) return <span className="badge badge-xs badge-success">Fresh</span>
  if (picksSince <= 2) return <span className="badge badge-xs badge-warning">{picksSince} picks ago</span>
  return <span className="badge badge-xs badge-error">{picksSince} picks ago</span>
}

function SourceBadge({ source }) {
  if (source === 'ai') return <span className="badge badge-xs badge-accent">AI</span>
  return <span className="badge badge-xs badge-ghost">Engine</span>
}

const priorityColors = {
  'must-have': 'text-error font-semibold',
  'strong-target': 'text-warning',
  'nice-to-have': 'text-info',
}

export default function RosterOptimizer({ optimizer, planStaleness }) {
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchPlan = async () => {
    setLoading(true)
    setError(null)
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 20000)
      const res = await fetch(`${API_BASE}/draft-plan`, { signal: controller.signal })
      clearTimeout(timeout)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setPlan(data)
    } catch (e) {
      setError(e.name === 'AbortError' ? 'Request timed out' : e.message)
    } finally {
      setLoading(false)
    }
  }

  // Sync staleness from server snapshot into local plan
  const displayPlan = plan
    ? { ...plan, picks_since_plan: planStaleness ?? plan.picks_since_plan }
    : null

  if (!optimizer || !optimizer.optimal_picks || optimizer.optimal_picks.length === 0) {
    return (
      <div className="card bg-base-200 shadow-md">
        <div className="card-body p-4">
          <h2 className="card-title text-sm text-primary">Optimal Remaining Picks</h2>
          <p className="text-xs opacity-50">Roster is full or no picks available.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        {/* Optimizer section */}
        <div className="flex items-center justify-between mb-1">
          <h2 className="card-title text-sm text-primary">Optimal Remaining Picks</h2>
          {optimizer.slots_to_fill > 0 && (
            <span className="badge badge-sm badge-info">
              {optimizer.slots_to_fill} starter{optimizer.slots_to_fill !== 1 ? 's' : ''}
              {optimizer.bench_to_fill > 0 && ` + ${optimizer.bench_to_fill} bench`}
            </span>
          )}
        </div>
        <div className="space-y-1 max-h-56 overflow-y-auto">
          {(optimizer.starter_picks || optimizer.optimal_picks.filter(p => !p.is_bench)).map((p, i) => (
            <div key={p.player} className="flex items-center justify-between text-xs bg-base-300 rounded-lg px-3 py-1.5">
              <div className="flex-1 min-w-0">
                <span className="opacity-40 mr-1">{i + 1}.</span>
                <span className="font-medium">{p.player}</span>
                <span className="badge badge-xs badge-ghost ml-1">{p.position}</span>
                {p.tier && <span className="opacity-40 ml-1">T{p.tier}</span>}
              </div>
              <div className="flex gap-2 text-right whitespace-nowrap">
                <span className="opacity-50">VORP {p.vorp}</span>
                <span className="text-success font-mono">~${p.estimated_price}</span>
              </div>
            </div>
          ))}
          {(optimizer.bench_picks || optimizer.optimal_picks.filter(p => p.is_bench)).length > 0 && (
            <>
              <div className="text-[10px] opacity-40 text-center py-0.5">— BENCH ($1 each) —</div>
              {(optimizer.bench_picks || optimizer.optimal_picks.filter(p => p.is_bench)).map((p, i) => (
                <div key={p.player} className="flex items-center justify-between text-xs bg-base-300/50 rounded-lg px-3 py-1">
                  <div className="flex-1 min-w-0">
                    <span className="font-medium opacity-60">{p.player}</span>
                    <span className="badge badge-xs badge-ghost ml-1">{p.position}</span>
                  </div>
                  <span className="text-success font-mono opacity-50">$1</span>
                </div>
              ))}
            </>
          )}
        </div>
        <div className="flex justify-between text-[11px] opacity-50 mt-2 pt-2 border-t border-base-300">
          <span>Starters: ${optimizer.starter_cost ?? optimizer.total_estimated_cost}</span>
          <span>+{optimizer.projected_points_added} pts</span>
          <span>${optimizer.remaining_budget_after} left</span>
        </div>

        {/* AI Draft Plan section */}
        <div className="mt-3 pt-3 border-t border-base-300">
          <div className="flex items-center gap-2 mb-2">
            <button
              className={`btn btn-xs ${displayPlan ? 'btn-ghost' : 'btn-primary'}`}
              onClick={fetchPlan}
              disabled={loading}
            >
              {loading && <span className="loading loading-spinner loading-xs" />}
              {displayPlan ? 'Refresh AI Plan' : 'Generate AI Draft Plan'}
            </button>
            {displayPlan && (
              <div className="flex gap-1">
                <StalenessBadge picksSince={displayPlan.picks_since_plan} />
                <SourceBadge source={displayPlan.source} />
              </div>
            )}
          </div>

          {error && (
            <p className="text-xs text-error">{error}</p>
          )}

          {displayPlan && !loading && (
            <div className="space-y-2">
              {/* Strategy summary */}
              <p className="text-xs opacity-80">{displayPlan.strategy_summary}</p>

              {/* Spending plan */}
              {displayPlan.spending_plan?.length > 0 && (
                <div>
                  <h3 className="text-[11px] font-semibold opacity-60 mb-1">Spending Plan</h3>
                  <div className="space-y-0.5">
                    {displayPlan.spending_plan.map((s) => (
                      <div key={s.position} className="flex items-center justify-between text-xs bg-base-300 rounded px-2 py-1">
                        <div className="flex items-center gap-1">
                          <span className="badge badge-xs badge-ghost">{s.position}</span>
                          <span className="opacity-50 capitalize">{s.tier_target}</span>
                        </div>
                        <span className="font-mono text-success">${s.budget_allocation}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Key targets */}
              {displayPlan.key_targets?.length > 0 && (
                <div>
                  <h3 className="text-[11px] font-semibold opacity-60 mb-1">Key Targets</h3>
                  <div className="space-y-1">
                    {displayPlan.key_targets.map((t) => (
                      <div key={t.player} className="text-xs bg-base-300 rounded px-2 py-1">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1">
                            <span className="font-medium">{t.player}</span>
                            <span className="badge badge-xs badge-ghost">{t.position}</span>
                            <span className={`text-[10px] ${priorityColors[t.priority] || 'opacity-50'}`}>
                              {t.priority}
                            </span>
                          </div>
                          <span className="font-mono whitespace-nowrap">
                            ${t.price_range?.[0]}-${t.price_range?.[1]}
                          </span>
                        </div>
                        {t.reasoning && (
                          <p className="text-[10px] opacity-50 mt-0.5">{t.reasoning}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Bargain picks */}
              {displayPlan.bargain_picks?.length > 0 && (
                <div>
                  <h3 className="text-[11px] font-semibold opacity-60 mb-1">Bargain Picks</h3>
                  <div className="space-y-1">
                    {displayPlan.bargain_picks.map((b) => (
                      <div key={b.player} className="text-xs bg-base-300 rounded px-2 py-1">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1">
                            <span className="font-medium">{b.player}</span>
                            <span className="badge badge-xs badge-ghost">{b.position}</span>
                            <span className="text-[10px] text-success">value</span>
                          </div>
                          <span className="font-mono whitespace-nowrap">
                            ${b.price_range?.[0]}-${b.price_range?.[1]}
                          </span>
                        </div>
                        {b.reasoning && (
                          <p className="text-[10px] opacity-50 mt-0.5">{b.reasoning}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Avoid list */}
              {displayPlan.avoid_list?.length > 0 && (
                <div className="text-xs">
                  <span className="font-semibold opacity-60 text-[11px]">Avoid: </span>
                  <span className="opacity-50">{displayPlan.avoid_list.join(', ')}</span>
                </div>
              )}

              {/* Budget reserve footer */}
              {displayPlan.budget_reserve > 0 && (
                <div className="text-[11px] opacity-50 pt-1 border-t border-base-300">
                  Budget reserve: ${displayPlan.budget_reserve}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
