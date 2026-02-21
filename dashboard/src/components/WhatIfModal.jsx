import { useState } from 'react'
import { API_BASE } from '../hooks/useDraftState'

export default function WhatIfModal({ player, onClose }) {
  const [price, setPrice] = useState(Math.round(player.fmv || 1))
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleSimulate = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(
        `${API_BASE}/whatif?player=${encodeURIComponent(player.name)}&price=${price}`
      )
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        setResult(data)
      }
    } catch (e) {
      setError(e.message || 'Failed to fetch simulation')
    } finally {
      setLoading(false)
    }
  }

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div className="modal modal-open" onClick={handleBackdropClick}>
      <div className="modal-box bg-base-200 max-w-lg relative">
        {/* Close button */}
        <button
          className="btn btn-sm btn-circle btn-ghost absolute right-2 top-2"
          onClick={onClose}
        >
          X
        </button>

        {/* Header */}
        <h3 className="font-bold text-lg text-primary mb-1">What-If Simulator</h3>
        <p className="text-sm opacity-70 mb-4">
          {player.name}
          <span className="badge badge-xs badge-ghost ml-2">{player.position}</span>
        </p>

        {/* Price input + simulate */}
        <div className="flex items-end gap-2 mb-4">
          <div className="form-control flex-1">
            <label className="label py-1">
              <span className="label-text text-xs">Purchase price ($)</span>
            </label>
            <input
              type="number"
              min={1}
              value={price}
              onChange={(e) => setPrice(Math.max(1, parseInt(e.target.value) || 1))}
              className="input input-bordered input-sm w-full"
            />
          </div>
          <button
            className="btn btn-sm btn-primary"
            onClick={handleSimulate}
            disabled={loading}
          >
            {loading && <span className="loading loading-spinner loading-xs" />}
            Simulate
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="alert alert-error text-xs mb-4">
            <span>{error}</span>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-3">
            {/* Summary row */}
            <div className="flex items-center justify-between text-sm">
              <div>
                <span className="opacity-60">Budget after: </span>
                <span className="font-mono text-success font-semibold">
                  ${result.remaining_budget_after}
                </span>
              </div>
              <div>
                <span className="opacity-60">Roster: </span>
                <span className="badge badge-sm badge-info">{result.roster_completeness}</span>
              </div>
            </div>

            {/* Projected total */}
            <div className="text-sm">
              <span className="opacity-60">Projected total: </span>
              <span className={`font-mono font-semibold ${result.projected_total_points >= 1800 ? 'text-success' : result.projected_total_points >= 1600 ? 'text-warning' : 'text-error'}`}>
                {result.projected_total_points} pts
              </span>
            </div>

            {/* Optimal remaining picks */}
            {result.optimal_remaining_picks?.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold opacity-60 mb-1">Optimal Remaining Picks</h4>
                <div className="overflow-x-auto max-h-48">
                  <table className="table table-xs">
                    <thead>
                      <tr>
                        <th className="text-xs">Player</th>
                        <th className="text-xs text-center">Pos</th>
                        <th className="text-xs text-right">Est. Price</th>
                        <th className="text-xs text-right">VORP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.optimal_remaining_picks.map((pick) => (
                        <tr key={pick.player}>
                          <td className="text-xs">{pick.player}</td>
                          <td className="text-xs text-center">
                            <span className="badge badge-xs badge-ghost">{pick.position}</span>
                          </td>
                          <td className="text-xs text-right font-mono">${pick.estimated_price}</td>
                          <td className="text-xs text-right font-mono">{pick.vorp}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
