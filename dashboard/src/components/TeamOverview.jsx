import { useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function TeamOverview({ budgets, myTeam, opponentNeeds }) {
  const [editing, setEditing] = useState(null)
  const [editValue, setEditValue] = useState('')

  if (!budgets || Object.keys(budgets).length === 0) return null

  const myTeamName = myTeam?.team_name?.toLowerCase() || ''

  // Build team rows from budgets (includes all teams)
  const teams = Object.entries(budgets).map(([team, budget]) => ({
    team,
    budget,
    isMe: myTeamName.split(',').some(a => a.trim() === team.toLowerCase()),
  })).sort((a, b) => b.budget - a.budget)

  const maxBudget = Math.max(200, ...teams.map(d => d.budget))

  // Map budget display names → team_ids using the backend-provided mapping
  const rosters = opponentNeeds?.team_rosters || {}
  const nameToId = opponentNeeds?.name_to_id || {}
  // Also build a fallback from threat display_names
  const threats = opponentNeeds?.threat_levels || []
  const threatById = {}
  for (const t of threats) {
    threatById[t.team_id] = t
    // Fallback: also map display_name → team_id
    if (t.display_name && !nameToId[t.display_name]) {
      nameToId[t.display_name] = t.team_id
    }
  }

  // Default position columns — always shown, enriched by roster data if available
  const DEFAULT_POSITIONS = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']
  const dataPositions = new Set(
    Object.values(rosters).flatMap(r => Object.keys(r))
  )
  const positions = DEFAULT_POSITIONS.filter(p =>
    !['BENCH', 'IR', 'UNK'].includes(p)
  )
  // Add any extra positions from data that aren't in defaults
  for (const p of dataPositions) {
    if (!['BENCH', 'IR', 'UNK'].includes(p) && !positions.includes(p)) {
      positions.push(p)
    }
  }

  function startEdit(team) {
    setEditing(team)
    setEditValue(team)
  }

  async function saveAlias(originalName) {
    const newName = editValue.trim()
    setEditing(null)
    if (!newName || newName === originalName) return
    try {
      await fetch(`${API_BASE}/team_aliases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [originalName]: newName }),
      })
    } catch (err) {
      console.error('Failed to save team alias:', err)
    }
  }

  function handleKeyDown(e, team) {
    if (e.key === 'Enter') saveAlias(team)
    if (e.key === 'Escape') setEditing(null)
  }

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">
          Team Budgets &amp; Needs
          <span className="text-[10px] opacity-30 font-normal ml-1">(click name to rename)</span>
        </h2>
        <div className="overflow-x-auto">
          <table className="table table-xs">
            <thead>
              <tr>
                <th className="w-24">Team</th>
                <th className="min-w-[80px]">Budget</th>
                <th className="text-right w-10">$</th>
                {positions.map(p => (
                  <th key={p} className="text-center w-8">{p}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {teams.map(d => {
                const teamId = nameToId[d.team]
                const rosterCounts = teamId ? (rosters[teamId] || {}) : {}

                return (
                  <tr key={d.team} className={d.isMe ? 'bg-primary/10' : ''}>
                    <td>
                      {editing === d.team ? (
                        <input
                          className="input input-xs input-bordered w-24"
                          value={editValue}
                          onChange={e => setEditValue(e.target.value)}
                          onBlur={() => saveAlias(d.team)}
                          onKeyDown={e => handleKeyDown(e, d.team)}
                          autoFocus
                        />
                      ) : (
                        <span
                          className={`truncate cursor-pointer hover:underline ${d.isMe ? 'text-primary font-semibold' : 'opacity-70'}`}
                          onClick={() => startEdit(d.team)}
                          title="Click to rename"
                        >
                          {d.team}
                        </span>
                      )}
                    </td>
                    <td>
                      <progress
                        className="progress progress-primary h-2.5 w-full"
                        value={d.budget}
                        max={maxBudget}
                      />
                    </td>
                    <td className="text-right font-mono">${d.budget}</td>
                    {positions.map(pos => {
                      const count = rosterCounts[pos] || 0
                      return (
                        <td key={pos} className="text-center">
                          <span className={count > 0 ? '' : 'opacity-20'}>
                            {count}
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
