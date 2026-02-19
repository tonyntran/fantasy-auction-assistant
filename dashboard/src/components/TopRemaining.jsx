import { useState } from 'react'

function PlayerNewsBadges({ news }) {
  if (!news) return null
  return (
    <>
      {news.team && <span className="opacity-40 text-[10px]">{news.team}</span>}
      {news.injury_status && (
        <span
          className={`badge badge-xs ${news.injury_status === 'Out' || news.injury_status === 'IR' ? 'badge-error' : 'badge-warning'}`}
          title={`${news.injury_status}${news.injury ? ` (${news.injury})` : ''}`}
        >
          {news.injury_status}
        </span>
      )}
      {!news.injury_status && news.recent_news && (
        <span className="badge badge-xs badge-info" title="Recent news — check Sleeper for details">NEW</span>
      )}
      {!news.active && !news.injury_status && (
        <span className="badge badge-xs badge-error">{news.status || 'Inactive'}</span>
      )}
    </>
  )
}

function chipStyle(news) {
  if (news.injury_status === 'Out' || news.injury_status === 'IR') return 'badge-error'
  if (news.injury_status) return 'badge-warning'
  if (!news.active) return 'badge-error'
  if (news.recent_news) return 'badge-info'
  return 'badge-ghost'
}

function chipLabel(news) {
  if (news.injury_status) return news.injury_status
  if (!news.active) return news.status || 'Inactive'
  if (news.recent_news) return 'NEW'
  return ''
}

export default function TopRemaining({ topRemaining, playerNews = {}, positionalVona = [] }) {
  const [selected, setSelected] = useState(null)

  if (!topRemaining) return null

  const positions = Object.keys(topRemaining)

  // All players with notable news, sorted by most recent update
  const newsEntries = Object.entries(playerNews)
    .filter(([, n]) => n.summary)
    .sort(([, a], [, b]) => (b.news_updated || 0) - (a.news_updated || 0))

  const selectedNews = selected ? playerNews[selected] : null

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Top Remaining <span className="text-[10px] opacity-40 font-normal">(VORP / FMV)</span></h2>

        {/* Cross-positional VONA — position priority by drop-off */}
        {positionalVona.length > 0 && (
          <div className="flex gap-1.5 flex-wrap mb-1">
            {positionalVona.map((pv, i) => (
              <div
                key={pv.position}
                className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                  i === 0 ? 'bg-error/20 text-error font-semibold' : 'bg-base-300 opacity-60'
                }`}
                title={`${pv.top_player} → ${pv.next_player}: ${pv.vona} szn / ${pv.vona_per_game}/gm drop-off`}
              >
                {pv.position} {pv.vona_per_game}/gm
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          {positions.map(pos => (
            <div key={pos}>
              <h3 className="text-xs font-bold opacity-50 mb-1">{pos}</h3>
              <ul className="space-y-0.5">
                {(topRemaining[pos] || []).map((p) => (
                  <li key={p.name}>
                    <div className="flex items-center justify-between text-xs gap-1">
                      <span className="truncate flex items-center gap-1">
                        <span
                          className={playerNews[p.name] ? 'cursor-pointer hover:text-primary' : ''}
                          onClick={() => playerNews[p.name] && setSelected(selected === p.name ? null : p.name)}
                        >
                          {p.name}
                        </span>
                        <PlayerNewsBadges news={playerNews[p.name]} />
                      </span>
                      <span className="whitespace-nowrap font-mono">
                        <span className="opacity-40 mr-1">{p.vorp}</span>
                        <span className="text-success">${p.fmv}</span>
                      </span>
                    </div>
                    {p.tier_break && (
                      <div className="flex items-center gap-1 my-0.5">
                        <div className="flex-1 border-t border-dashed border-error/40"></div>
                        <span className="text-[9px] text-error opacity-60">-{p.drop_off} pts</span>
                        <div className="flex-1 border-t border-dashed border-error/40"></div>
                      </div>
                    )}
                  </li>
                ))}
                {(!topRemaining[pos] || topRemaining[pos].length === 0) && (
                  <li className="text-xs opacity-30">None</li>
                )}
              </ul>
            </div>
          ))}
        </div>

        {/* Player news ticker */}
        {newsEntries.length > 0 && (
          <div className="mt-2 pt-2 border-t border-base-300">
            <div className="flex overflow-x-auto gap-1.5 pb-1 scrollbar-thin">
              {newsEntries.map(([name, news]) => (
                <button
                  key={name}
                  onClick={() => setSelected(selected === name ? null : name)}
                  className={`badge badge-sm whitespace-nowrap cursor-pointer flex-shrink-0 gap-1 ${
                    selected === name ? 'badge-primary' : chipStyle(news)
                  }`}
                >
                  {name.split(' ').pop()}
                  <span className="text-[9px] opacity-70">{chipLabel(news)}</span>
                </button>
              ))}
            </div>

            {/* Expanded detail for selected player */}
            {selectedNews && (
              <div className="mt-1.5 bg-base-300 rounded-lg px-3 py-2 text-xs">
                <div className="flex items-center justify-between mb-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{selected}</span>
                    <PlayerNewsBadges news={selectedNews} />
                  </div>
                  {selectedNews.news_date && (
                    <span className="opacity-40 text-[10px]">{selectedNews.news_date}</span>
                  )}
                </div>
                <p className="opacity-70">{selectedNews.summary}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
