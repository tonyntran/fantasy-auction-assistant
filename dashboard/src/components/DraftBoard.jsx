import { useState } from 'react'
import usePersistedState from '../hooks/usePersistedState'
import ErrorBoundary from './ErrorBoundary'
import WhatIfModal from './WhatIfModal'
import PlayerComparison from './PlayerComparison'

const MAX_COMPARE = 3

export default function DraftBoard({ players, positions = [], positionBadges = {}, playerNews = {} }) {
  const [filter, setFilter] = usePersistedState('positionFilter', 'ALL')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('desc')
  const [whatIfPlayer, setWhatIfPlayer] = useState(null)
  const [compareMode, setCompareMode] = useState(false)
  const [compareList, setCompareList] = useState([])
  const [showComparison, setShowComparison] = useState(false)

  const toggleCompareMode = () => {
    if (compareMode) {
      setCompareList([])
      setShowComparison(false)
    }
    setCompareMode(prev => !prev)
  }

  const togglePlayer = (player) => {
    setCompareList(prev => {
      const exists = prev.find(p => p.name === player.name)
      if (exists) return prev.filter(p => p.name !== player.name)
      if (prev.length >= MAX_COMPARE) return prev
      return [...prev, player]
    })
  }

  const isSelected = (name) => compareList.some(p => p.name === name)
  const atLimit = compareList.length >= MAX_COMPARE

  if (!players) return null

  const filterButtons = ['ALL', ...positions]

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir(prev => prev === 'desc' ? 'asc' : 'desc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sortIndicator = (key) => {
    if (sortKey !== key) return null
    return <span className="ml-1">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
  }

  const filtered = players
    .filter(p => filter === 'ALL' || p.position === filter)
    .filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      // Drafted players always at the bottom
      if (a.is_drafted !== b.is_drafted) return a.is_drafted ? 1 : -1

      // Default sort: VORP descending
      if (!sortKey) return b.vorp - a.vorp

      // Custom column sort
      const dir = sortDir === 'asc' ? 1 : -1
      let aVal, bVal
      switch (sortKey) {
        case 'name':
          aVal = (a.name || '').toLowerCase()
          bVal = (b.name || '').toLowerCase()
          return aVal < bVal ? -dir : aVal > bVal ? dir : 0
        case 'position':
          aVal = (a.position || '').toLowerCase()
          bVal = (b.position || '').toLowerCase()
          return aVal < bVal ? -dir : aVal > bVal ? dir : 0
        case 'tier':
          return ((a.tier || 0) - (b.tier || 0)) * dir
        case 'fmv':
          return ((a.fmv || 0) - (b.fmv || 0)) * dir
        case 'vorp':
          return ((a.vorp || 0) - (b.vorp || 0)) * dir
        case 'vona':
          return ((a.vona || 0) - (b.vona || 0)) * dir
        case 'draft_price':
          return ((a.draft_price || 0) - (b.draft_price || 0)) * dir
        default:
          return b.vorp - a.vorp
      }
    })

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <h2 className="card-title text-sm text-primary">Draft Board</h2>
            <button
              onClick={toggleCompareMode}
              className={`btn btn-xs ${compareMode ? 'btn-primary' : 'btn-ghost'}`}
            >
              Compare
            </button>
          </div>
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
                {compareMode && <th className="w-8"></th>}
                <th className="cursor-pointer hover:text-primary select-none" onClick={() => handleSort('name')}>
                  Player{sortIndicator('name')}
                </th>
                <th className="text-center cursor-pointer hover:text-primary select-none" onClick={() => handleSort('position')}>
                  Pos{sortIndicator('position')}
                </th>
                <th className="text-center cursor-pointer hover:text-primary select-none" onClick={() => handleSort('tier')}>
                  T{sortIndicator('tier')}
                </th>
                <th className="text-right cursor-pointer hover:text-primary select-none" onClick={() => handleSort('fmv')}>
                  FMV{sortIndicator('fmv')}
                </th>
                <th className="text-right cursor-pointer hover:text-primary select-none" onClick={() => handleSort('vorp')}>
                  VORP{sortIndicator('vorp')}
                </th>
                <th className="text-right cursor-pointer hover:text-primary select-none" onClick={() => handleSort('vona')}>
                  VONA{sortIndicator('vona')}
                </th>
                <th className="text-right cursor-pointer hover:text-primary select-none" onClick={() => handleSort('draft_price')}>
                  Price{sortIndicator('draft_price')}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => (
                <tr key={p.name} className={`${p.is_drafted ? 'opacity-30' : ''}${compareMode && isSelected(p.name) ? ' bg-primary/10' : ''}`}>
                  {compareMode && (
                    <td className="text-center w-8 px-1">
                      {!p.is_drafted && (
                        <input
                          type="checkbox"
                          className="checkbox checkbox-xs checkbox-primary"
                          checked={isSelected(p.name)}
                          disabled={!isSelected(p.name) && atLimit}
                          onChange={() => togglePlayer(p)}
                        />
                      )}
                    </td>
                  )}
                  <td>
                    <span
                      className={`${p.drafted_by === 'My Team' || p.drafted_by?.toLowerCase() === (import.meta.env.VITE_MY_TEAM || 'my team') ? 'text-primary font-medium' : ''}${!p.is_drafted ? ' cursor-pointer hover:text-primary hover:underline' : ''}`}
                      onClick={!p.is_drafted ? () => setWhatIfPlayer(p) : undefined}
                    >
                      {p.name}
                    </span>
                    {p.is_keeper && <span className="badge badge-xs badge-accent ml-1">K</span>}
                    {!p.is_drafted && playerNews[p.name] && (() => {
                      const news = playerNews[p.name]
                      return (
                        <>
                          {news.team && <span className="opacity-40 text-[10px] ml-1">{news.team}</span>}
                          {news.injury_status && (
                            <span className={`badge badge-xs ml-1 ${news.injury_status === 'Out' || news.injury_status === 'IR' ? 'badge-error' : 'badge-warning'}`} title={`${news.injury_status}${news.injury ? ` (${news.injury})` : ''}`}>
                              {news.injury_status}
                            </span>
                          )}
                          {!news.injury_status && news.recent_news && (
                            <span className="badge badge-xs badge-info ml-1" title="Recent news — check Sleeper for details">NEW</span>
                          )}
                          {!news.active && !news.injury_status && (
                            <span className="badge badge-xs badge-error ml-1">{news.status || 'Inactive'}</span>
                          )}
                        </>
                      )
                    })()}
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

      {whatIfPlayer && (
        <ErrorBoundary name="What-If Modal">
          <WhatIfModal player={whatIfPlayer} onClose={() => setWhatIfPlayer(null)} />
        </ErrorBoundary>
      )}

      {compareMode && compareList.length >= 2 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-base-300 shadow-lg rounded-lg px-4 py-2 flex items-center gap-3">
          <span className="text-sm font-medium">{compareList.length} selected</span>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => setShowComparison(true)}
          >
            Compare Players
          </button>
          <button
            className="btn btn-sm btn-ghost"
            onClick={() => setCompareList([])}
          >
            Clear
          </button>
        </div>
      )}

      {showComparison && (
        <ErrorBoundary name="Player Comparison">
          <PlayerComparison
            players={compareList}
            onClose={() => setShowComparison(false)}
          />
        </ErrorBoundary>
      )}
    </div>
  )
}
