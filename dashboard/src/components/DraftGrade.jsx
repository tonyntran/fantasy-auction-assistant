import { useState } from 'react'
import { API_BASE } from '../hooks/useDraftState'

const GRADE_COLORS = {
  'A+': 'text-success', 'A': 'text-success', 'A-': 'text-success',
  'B+': 'text-info', 'B': 'text-info', 'B-': 'text-info',
  'C+': 'text-warning', 'C': 'text-warning', 'C-': 'text-warning',
  'D+': 'text-error', 'D': 'text-error', 'D-': 'text-error',
  'F': 'text-error',
}

function getGradeColor(grade) {
  if (!grade) return 'text-base-content'
  // Match the letter portion (e.g. "A+" from "A+")
  const normalized = grade.trim().toUpperCase().replace(/[^A-F+-]/g, '')
  return GRADE_COLORS[normalized] || 'text-base-content'
}

function PositionGrades({ grades }) {
  if (!grades || typeof grades !== 'object') return null
  const entries = Object.entries(grades)
  if (entries.length === 0) return null

  return (
    <div>
      <h3 className="text-[11px] font-semibold opacity-60 mb-1">Position Grades</h3>
      <div className="flex flex-wrap gap-1">
        {entries.map(([pos, grade]) => (
          <div key={pos} className="flex items-center gap-1 bg-base-300 rounded px-2 py-1 text-xs">
            <span className="badge badge-xs badge-ghost">{pos}</span>
            <span className={`font-bold ${getGradeColor(grade)}`}>{grade}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function PickHighlight({ label, pick, colorClass }) {
  if (!pick) return null
  return (
    <div className="text-xs bg-base-300 rounded px-3 py-2">
      <span className={`font-semibold ${colorClass}`}>{label}:</span>{' '}
      <span className="font-medium">{pick.name}</span>
      {pick.reasoning && (
        <p className="text-[10px] opacity-50 mt-0.5">{pick.reasoning}</p>
      )}
    </div>
  )
}

function EngineFallback({ grade }) {
  return (
    <div className="space-y-2">
      <div className="text-center py-2">
        <div className="text-[10px] opacity-40 uppercase tracking-wide">Engine Analysis</div>
        <div className="text-xs opacity-60 mt-1">AI grading unavailable — showing statistical summary</div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="bg-base-300 rounded px-3 py-2 text-center">
          <div className="opacity-40 text-[10px]">Spent</div>
          <div className="font-mono font-bold">${grade.total_spent}</div>
        </div>
        <div className="bg-base-300 rounded px-3 py-2 text-center">
          <div className="opacity-40 text-[10px]">Projected Pts</div>
          <div className="font-mono font-bold">{grade.total_projected_points}</div>
        </div>
        <div className={`bg-base-300 rounded px-3 py-2 text-center ${grade.total_surplus_value >= 0 ? 'text-success' : 'text-error'}`}>
          <div className="opacity-40 text-[10px] text-base-content">Surplus Value</div>
          <div className="font-mono font-bold">${grade.total_surplus_value}</div>
        </div>
      </div>
      {grade.picks?.length > 0 && (
        <div>
          <h3 className="text-[11px] font-semibold opacity-60 mb-1">Picks ({grade.picks.length})</h3>
          <div className="space-y-0.5 max-h-32 overflow-y-auto">
            {grade.picks.map((p) => (
              <div key={p.name} className="flex items-center justify-between text-xs bg-base-300 rounded px-2 py-1">
                <span className="font-medium">{p.name}</span>
                <span className="font-mono opacity-50">${p.price}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function DraftGrade({ myTeam, rosterSize }) {
  const [grade, setGrade] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const acquired = myTeam?.players_acquired?.length ?? 0
  const completionPct = rosterSize > 0 ? acquired / rosterSize : 0
  const canGrade = completionPct >= 0.8

  const fetchGrade = async () => {
    setLoading(true)
    setError(null)
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 30000)
      const res = await fetch(`${API_BASE}/grade`, { signal: controller.signal })
      clearTimeout(timeout)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setGrade(data)
    } catch (e) {
      setError(e.name === 'AbortError' ? 'Request timed out (AI grading can be slow)' : e.message)
    } finally {
      setLoading(false)
    }
  }

  const dismiss = () => {
    setGrade(null)
    setError(null)
  }

  if (!canGrade) return null

  const isEngineOnly = grade?.source === 'engine'
  const isAiGrade = grade && !isEngineOnly && grade.overall_grade && !grade.overall_grade.includes('N/A')

  return (
    <div className="card bg-base-200 shadow-md">
      <div className="card-body p-4">
        <div className="flex items-center justify-between">
          <h2 className="card-title text-sm text-primary">Draft Grade</h2>
          <div className="flex items-center gap-2">
            {grade && (
              <button className="btn btn-xs btn-ghost opacity-50" onClick={dismiss}>
                Close
              </button>
            )}
            <span className="text-[10px] opacity-40">{acquired}/{rosterSize} filled</span>
          </div>
        </div>

        {/* Button: show when no grade loaded */}
        {!grade && !loading && (
          <button
            className="btn btn-secondary btn-sm mt-1"
            onClick={fetchGrade}
            disabled={loading}
          >
            Grade My Draft
          </button>
        )}

        {/* Loading state */}
        {loading && (
          <div className="flex items-center gap-2 py-4 justify-center">
            <span className="loading loading-spinner loading-sm text-secondary" />
            <span className="text-xs opacity-60">AI is grading your draft...</span>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="text-xs text-error mt-2">
            {error}
            <button className="btn btn-xs btn-ghost ml-2" onClick={fetchGrade}>
              Retry
            </button>
          </div>
        )}

        {/* Engine-only fallback */}
        {grade && isEngineOnly && !loading && (
          <EngineFallback grade={grade} />
        )}

        {/* Raw text fallback (JSON parse failed on backend) */}
        {grade && grade.raw_text && !loading && (
          <div className="text-xs whitespace-pre-wrap opacity-70 max-h-64 overflow-y-auto mt-2">
            {grade.raw_text}
          </div>
        )}

        {/* Full AI grade */}
        {isAiGrade && !loading && (
          <div className="space-y-3 mt-1">
            {/* Overall grade - prominent display */}
            <div className="text-center py-2">
              <div className="text-[10px] opacity-40 uppercase tracking-wide">Overall Grade</div>
              <div className={`text-5xl font-black ${getGradeColor(grade.overall_grade)}`}>
                {grade.overall_grade}
              </div>
              {grade.grade_explanation && (
                <p className="text-xs opacity-60 mt-1 max-w-xs mx-auto">{grade.grade_explanation}</p>
              )}
              {grade.projected_finish && (
                <div className="text-xs opacity-50 mt-1">
                  Projected finish: <span className="font-semibold text-base-content">{grade.projected_finish}</span>
                </div>
              )}
            </div>

            {/* Position grades */}
            <PositionGrades grades={grade.position_grades} />

            {/* Strengths and weaknesses */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {grade.strengths?.length > 0 && (
                <div>
                  <h3 className="text-[11px] font-semibold text-success mb-1">Strengths</h3>
                  <ul className="space-y-0.5">
                    {grade.strengths.map((s, i) => (
                      <li key={i} className="text-xs bg-base-300 rounded px-2 py-1 opacity-80">{s}</li>
                    ))}
                  </ul>
                </div>
              )}
              {grade.weaknesses?.length > 0 && (
                <div>
                  <h3 className="text-[11px] font-semibold text-error mb-1">Weaknesses</h3>
                  <ul className="space-y-0.5">
                    {grade.weaknesses.map((w, i) => (
                      <li key={i} className="text-xs bg-base-300 rounded px-2 py-1 opacity-80">{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Best and worst picks */}
            <div className="space-y-1">
              <PickHighlight label="Best Pick" pick={grade.best_pick} colorClass="text-success" />
              <PickHighlight label="Worst Pick" pick={grade.worst_pick} colorClass="text-error" />
            </div>

            {/* Waiver targets */}
            {grade.waiver_targets?.length > 0 && (
              <div>
                <h3 className="text-[11px] font-semibold opacity-60 mb-1">Waiver Wire Targets</h3>
                <div className="flex flex-wrap gap-1">
                  {grade.waiver_targets.map((name) => (
                    <span key={name} className="badge badge-sm badge-outline">{name}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Re-grade button */}
            <div className="pt-1 border-t border-base-300">
              <button className="btn btn-xs btn-ghost opacity-50" onClick={fetchGrade} disabled={loading}>
                Re-grade
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
