import { useState, useEffect } from 'react'

const STORAGE_KEY = 'faa_prefs'

function getStoredPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function setStoredPref(key, value) {
  try {
    const prefs = getStoredPrefs()
    prefs[key] = value
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // localStorage unavailable
  }
}

export default function usePersistedState(key, defaultValue) {
  const [value, setValue] = useState(() => {
    const stored = getStoredPrefs()[key]
    return stored !== undefined ? stored : defaultValue
  })

  useEffect(() => {
    setStoredPref(key, value)
  }, [key, value])

  return [value, setValue]
}
