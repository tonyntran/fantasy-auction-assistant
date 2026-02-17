import { useState, useEffect, useRef } from 'react'
import useWebSocket from './useWebSocket'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function useDraftState() {
  const { state: wsState, connected } = useWebSocket()
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(true)
  const hasWsData = useRef(false)

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

  return { state, connected, loading }
}
