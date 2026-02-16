import { LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'

export default function InflationGraph({ history }) {
  if (!history || history.length < 2) return null

  const data = history.map(([ts, factor], i) => ({
    pick: i + 1,
    inflation: Number(factor.toFixed(3)),
  }))

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <h2 className="card-title text-sm text-primary">Inflation Over Time</h2>
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={data}>
            <XAxis dataKey="pick" tick={{ fontSize: 10, fill: 'oklch(var(--bc) / 0.4)' }} />
            <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: 'oklch(var(--bc) / 0.4)' }} width={40} />
            <Tooltip
              contentStyle={{
                background: 'oklch(var(--b2))',
                border: '1px solid oklch(var(--b3))',
                borderRadius: '0.5rem',
                fontSize: 11,
              }}
            />
            <ReferenceLine y={1} stroke="oklch(var(--bc) / 0.2)" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="inflation" stroke="oklch(var(--p))" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
