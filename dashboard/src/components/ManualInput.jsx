import { useState, useRef } from 'react'
import { API_BASE } from '../hooks/useDraftState'

const COMMANDS = [
  { syntax: 'sold PlayerName Price [TeamId]', desc: 'Record a sale' },
  { syntax: 'undo PlayerName', desc: 'Reverse a sale' },
  { syntax: 'budget N', desc: 'Adjust your budget' },
  { syntax: 'nom PlayerName [Price]', desc: 'Set a nomination' },
  { syntax: 'suggest', desc: 'Get AI suggestion' },
]

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
        [{ cmd: command.trim(), result: data.advice || 'Done', ok: res.ok }, ...prev].slice(0, 5)
      )
      setCommand('')
      if (res.ok && onCommandSuccess) onCommandSuccess()
    } catch (err) {
      setHistory((prev) =>
        [{ cmd: command.trim(), result: `Error: ${err.message}`, ok: false }, ...prev].slice(0, 5)
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
            <div className="mt-1 space-y-0.5">
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
          <div className="mt-2 space-y-1 max-h-36 overflow-y-auto">
            {history.map((h, i) => (
              <div key={`${h.cmd}-${i}`} className="bg-base-300 rounded px-2 py-1">
                <div className="text-xs font-mono opacity-50">&gt; {h.cmd}</div>
                <div className={`text-xs ${h.ok ? 'text-success' : 'text-error'} whitespace-pre-wrap break-words`}>
                  {h.result}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
