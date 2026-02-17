import { useState, useEffect, useRef, useCallback } from 'react'

const WS_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/^http/, 'ws') + '/ws'
const RECONNECT_DELAY_MS = 2000

export default function useWebSocket() {
  const [state, setState] = useState(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const timerRef = useRef(null)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (mountedRef.current) setConnected(true)
      }

      ws.onclose = () => {
        if (mountedRef.current) {
          setConnected(false)
          timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
        }
      }

      ws.onerror = () => {
        ws.close()
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'state_snapshot' && mountedRef.current) {
            setState(msg.data)
          }
        } catch {
          // ignore parse errors
        }
      }
    } catch {
      if (mountedRef.current) {
        timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(timerRef.current)
      if (wsRef.current) wsRef.current.close()
    }
  }, [connect])

  return { state, connected }
}
