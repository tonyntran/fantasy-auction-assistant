import { useEffect, useRef } from 'react'

const TYPE_BADGE = {
  NEW_NOMINATION: 'badge-info',
  BID_PLACED: 'badge-ghost',
  PLAYER_SOLD: 'badge-success',
  BUDGET_ALERT: 'badge-warning',
  MARKET_SHIFT: 'badge-secondary',
}

const TYPE_LABEL = {
  NEW_NOMINATION: 'NOM',
  BID_PLACED: 'BID',
  PLAYER_SOLD: 'SOLD',
  BUDGET_ALERT: 'ALERT',
  MARKET_SHIFT: 'SHIFT',
}

export default function ActivityFeed({ events }) {
  const scrollRef = useRef(null)

  const lastTimestamp = events?.[events.length - 1]?.timestamp

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [lastTimestamp, events?.length])

  if (!events || events.length === 0) {
    return (
      <div className="card bg-base-200 shadow-md">
        <div className="card-body p-4">
          <h2 className="card-title text-sm text-primary">Live Ticker</h2>
          <p className="text-xs opacity-50">No events yet — waiting for draft activity...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Live Ticker</h2>
        <div ref={scrollRef} className="max-h-48 overflow-y-auto space-y-1">
          {events.map((e, i) => (
            <div key={`${e.event_type}-${e.timestamp || i}`} className="flex items-start gap-2 text-xs">
              <span className={`badge badge-xs ${TYPE_BADGE[e.event_type] || 'badge-ghost'} shrink-0 mt-0.5`}>
                {TYPE_LABEL[e.event_type] || '?'}
              </span>
              <span className="opacity-80 leading-tight break-words min-w-0">{e.message}</span>
              {e.amount != null && (
                <span className="ml-auto font-mono opacity-50 shrink-0">${Math.round(e.amount)}</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
