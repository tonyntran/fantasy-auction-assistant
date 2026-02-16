import { useState, useEffect } from 'react'
import useWebSocket from './useWebSocket'

const API_BASE = 'http://localhost:8000'

export default function useDraftState() {
  const { state: wsState, connected } = useWebSocket()
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(true)

  // Initial fetch
  useEffect(() => {
    fetch(`${API_BASE}/dashboard/state`)
      .then((r) => r.json())
      .then((data) => {
        setState(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  // Update from WebSocket
  useEffect(() => {
    if (wsState) setState(wsState)
  }, [wsState])

  return { state, connected, loading }
}
