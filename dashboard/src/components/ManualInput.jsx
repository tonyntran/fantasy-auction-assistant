import { useState, useRef } from 'react'
import { API_BASE } from '../hooks/useDraftState'

const COMMANDS = [
  { syntax: 'sold PlayerName Price [TeamId]', desc: 'Record a sale' },
  { syntax: 'undo PlayerName', desc: 'Reverse a sale' },
  { syntax: 'budget N', desc: 'Adjust your budget' },
  { syntax: 'nom PlayerName [Price]', desc: 'Set a nomination' },
  { syntax: 'suggest', desc: 'Get AI suggestion' },
]

const STRATEGY_COLORS = {
  BUDGET_DRAIN: { bg: 'bg-orange-500/15', text: 'text-orange-400', border: 'border-orange-500/30' },
  RIVAL_DESPERATION: { bg: 'bg-red-500/15', text: 'text-red-400', border: 'border-red-500/30' },
  POISON_PILL: { bg: 'bg-purple-500/15', text: 'text-purple-400', border: 'border-purple-500/30' },
  BARGAIN_SNAG: { bg: 'bg-green-500/15', text: 'text-green-400', border: 'border-green-500/30' },
}

function SuggestionsGrid({ suggestions }) {
  return (
    <div className="mt-2">
      <div className="text-xs font-bold text-info mb-2">NOMINATION SUGGESTIONS</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-2">
        {suggestions.map((s, i) => {
          const colors = STRATEGY_COLORS[s.strategy] || { bg: 'bg-base-300', text: 'text-base-content', border: 'border-base-content/20' }
          return (
            <div key={i} className={`rounded-lg border ${colors.border} ${colors.bg} px-3 py-2`}>
              <div className="flex items-baseline justify-between gap-1">
                <span className="font-bold text-sm text-base-content">{s.player_name}</span>
                <span className="text-xs opacity-60">{s.position}</span>
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className={`text-[10px] font-mono font-semibold ${colors.text}`}>{s.strategy.replace('_', ' ')}</span>
                <span className="text-sm font-bold text-base-content">${s.fmv}</span>
              </div>
              <div className="text-[10px] opacity-50 mt-1 leading-tight">{s.reasoning}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ManualInput({ onCommandSuccess }) {
  const [command, setCommand] = useState('')
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [refOpen, setRefOpen] = useState(false)
  const inputRef = useRef(null)

  const submit = async () => {
    if (!command.trim() || loading) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: command.trim() }),
      })
      const data = await res.json()
      setHistory((prev) =>
        [{ cmd: command.trim(), result: data.advice || 'Done', ok: res.ok, suggestions: data.suggestions || null }, ...prev].slice(0, 5)
      )
      setCommand('')
      if (res.ok && onCommandSuccess) onCommandSuccess()
    } catch (err) {
      setHistory((prev) =>
        [{ cmd: command.trim(), result: `Error: ${err.message}`, ok: false, suggestions: null }, ...prev].slice(0, 5)
      )
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="collapse collapse-arrow bg-base-200 shadow-md">
      <input type="checkbox" />
      <div className="collapse-title text-sm font-medium text-primary py-3 min-h-0">
        Manual Command
      </div>
      <div className="collapse-content px-4 pb-4">
        {/* Input row */}
        <div className="flex gap-2 mt-1">
          <input
            ref={inputRef}
            type="text"
            className="input input-bordered input-sm flex-1 text-xs"
            placeholder='e.g. sold "Josh Allen" 45 or suggest'
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button
            className={`btn btn-primary btn-sm text-xs ${loading ? 'loading' : ''}`}
            onClick={submit}
            disabled={!command.trim() || loading}
          >
            {loading ? <span className="loading loading-spinner loading-xs" /> : 'Send'}
          </button>
        </div>

        {/* Command reference toggle */}
        <div className="mt-2">
          <button
            className="text-xs opacity-50 hover:opacity-80 underline"
            onClick={() => setRefOpen((o) => !o)}
          >
            {refOpen ? 'Hide' : 'Show'} command reference
          </button>
          {refOpen && (
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
              {COMMANDS.map((c) => (
                <div key={c.syntax} className="text-xs flex gap-2">
                  <code className="font-mono opacity-70">{c.syntax}</code>
                  <span className="opacity-50">-- {c.desc}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* History */}
        {history.length > 0 && (
          <div className="mt-2 space-y-2 max-h-64 overflow-y-auto">
            {history.map((h, i) => (
              <div key={`${h.cmd}-${i}`} className="bg-base-300 rounded px-3 py-2">
                <div className="text-xs font-mono opacity-50">&gt; {h.cmd}</div>
                {h.suggestions ? (
                  <SuggestionsGrid suggestions={h.suggestions} />
                ) : (
                  <div
                    className={`text-xs ${h.ok ? 'text-success' : 'text-error'} whitespace-pre-wrap break-words`}
                    dangerouslySetInnerHTML={{ __html: h.result }}
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
