import { API_BASE } from '../hooks/useDraftState'

export default function ExportButton({ myTeam, rosterSize }) {
  // Show when draft is mostly complete (60%+)
  const acquired = myTeam?.players_acquired?.length ?? 0
  const completionPct = rosterSize > 0 ? acquired / rosterSize : 0
  if (!completionPct || completionPct < 0.6) return null

  const exportJSON = async () => {
    const res = await fetch(`${API_BASE}/export?format=json`)
    const data = await res.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    downloadBlob(blob, 'draft_results.json')
  }

  const exportCSV = async () => {
    const res = await fetch(`${API_BASE}/export?format=csv`)
    const text = await res.text()
    const blob = new Blob([text], { type: 'text/csv' })
    downloadBlob(blob, 'draft_results.csv')
  }

  const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Export Draft Results</h2>
        <div className="flex gap-2">
          <button className="btn btn-sm btn-outline" onClick={exportJSON}>
            Export JSON
          </button>
          <button className="btn btn-sm btn-outline" onClick={exportCSV}>
            Export CSV
          </button>
        </div>
      </div>
    </div>
  )
}
