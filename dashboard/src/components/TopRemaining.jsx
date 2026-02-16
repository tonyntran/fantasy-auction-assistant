export default function TopRemaining({ topRemaining }) {
  if (!topRemaining) return null

  const positions = Object.keys(topRemaining)

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Top Remaining</h2>
        <div className="grid grid-cols-2 gap-3">
          {positions.map(pos => (
            <div key={pos}>
              <h3 className="text-xs font-bold opacity-50 mb-1">{pos}</h3>
              <ul className="space-y-1">
                {(topRemaining[pos] || []).map((p, i) => (
                  <li key={i} className="flex justify-between text-xs">
                    <span className="truncate mr-2">{p.name}</span>
                    <span className="text-success whitespace-nowrap font-mono">${p.fmv}</span>
                  </li>
                ))}
                {(!topRemaining[pos] || topRemaining[pos].length === 0) && (
                  <li className="text-xs opacity-30">None</li>
                )}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
