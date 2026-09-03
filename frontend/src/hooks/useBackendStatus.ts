import { useEffect, useState } from 'react'
import { checkHealth } from '../api/health'

export type BackendStatus = 'Checking...' | 'Online' | 'Offline'

export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>('Checking...')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const timeout = window.setTimeout(() => controller.abort(), 5000)

    checkHealth(controller.signal)
      .then(() => { if (active) setStatus('Online') })
      .catch(() => { if (active) setStatus('Offline') })
      .finally(() => window.clearTimeout(timeout))

    return () => {
      active = false
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [attempt])

  function retry() {
    setStatus('Checking...')
    setAttempt((current) => current + 1)
  }

  return { status, retry }
}
