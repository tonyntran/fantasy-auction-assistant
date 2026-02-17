import { useState } from 'react'

export default function DraftBoard({ players, positions = [], positionBadges = {} }) {
  const [filter, setFilter] = useState('ALL')
  const [search, setSearch] = useState('')

  if (!players) return null

  const filterButtons = ['ALL', ...positions]

  const filtered = players
    .filter(p => filter === 'ALL' || p.position === filter)
    .filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (a.is_drafted !== b.is_drafted) return a.is_drafted ? 1 : -1
      return b.vorp - a.vorp
    })

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="card-title text-sm text-primary">Draft Board</h2>
          <div className="join">
            {filterButtons.map(pos => (
              <button key={pos}
                onClick={() => setFilter(pos)}
                className={`join-item btn btn-xs ${filter === pos ? 'btn-primary' : 'btn-ghost'}`}>
                {pos}
              </button>
            ))}
          </div>
        </div>

        <input
          type="text" placeholder="Search players..."
          value={search} onChange={e => setSearch(e.target.value)}
          className="input input-bordered input-xs w-full mb-2"
        />

        <div className="overflow-x-auto max-h-80">
          <table className="table table-xs table-pin-rows">
            <thead>
              <tr>
                <th>Player</th>
                <th className="text-center">Pos</th>
                <th className="text-center">T</th>
                <th className="text-right">FMV</th>
                <th className="text-right">VORP</th>
                <th className="text-right">VONA</th>
                <th className="text-right">Price</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => (
                <tr key={p.name} className={p.is_drafted ? 'opacity-30' : ''}>
                  <td>
                    <span className={p.drafted_by === 'My Team' || p.drafted_by?.toLowerCase() === (import.meta.env.VITE_MY_TEAM || 'my team') ? 'text-primary font-medium' : ''}>
                      {p.name}
                    </span>
                  </td>
                  <td className="text-center">
                    <span className={`badge badge-xs ${positionBadges[p.position] || 'badge-ghost'}`}>
                      {p.position}
                    </span>
                  </td>
                  <td className="text-center opacity-50">{p.tier}</td>
                  <td className="text-right font-mono">${p.fmv}</td>
                  <td className="text-right font-mono">{p.vorp}</td>
                  <td className="text-right font-mono">
                    {!p.is_drafted && p.vona > 0 && (
                      <span className={p.vona >= 10 ? 'text-success font-bold' : ''} title={p.vona_next_player ? `Next: ${p.vona_next_player}` : ''}>
                        {p.vona}
                      </span>
                    )}
                  </td>
                  <td className="text-right opacity-50">{p.is_drafted ? `$${p.draft_price}` : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
