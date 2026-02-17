import { useState, useEffect, useRef, useCallback } from 'react'
import useWebSocket from './useWebSocket'

export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function useDraftState() {
  const { state: wsState, connected } = useWebSocket()
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(true)
  const hasWsData = useRef(false)

  const refetch = useCallback(() => {
    fetch(`${API_BASE}/dashboard/state`)
      .then((r) => r.json())
      .then((data) => setState(data))
      .catch(() => {})
  }, [])

  // Initial fetch
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/dashboard/state`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        // Skip if WebSocket already delivered fresher data
        if (!hasWsData.current) setState(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
    return () => controller.abort()
  }, [])

  // Update from WebSocket
  useEffect(() => {
    if (wsState) {
      hasWsData.current = true
      setState(wsState)
    }
  }, [wsState])

  return { state, setState, connected, loading, refetch }
}
