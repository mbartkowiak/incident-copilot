import { useEffect, useState } from 'react'
import { getJson } from './api'

export type ApiResult<T> = {
  data: T | undefined
  error: string | undefined
  loading: boolean
}

type Settled<T> = { path?: string; data?: T; error?: string }

// Keeps the previous data while a new request is in flight, so the UI dims instead of
// flashing a skeleton when a filter changes. "Loading" means the settled result is for
// a different path than the one requested.
export function useApi<T>(path: string): ApiResult<T> {
  const [settled, setSettled] = useState<Settled<T>>({})

  useEffect(() => {
    const controller = new AbortController()
    getJson<T>(path, controller.signal)
      .then((data) => setSettled({ path, data }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const error = err instanceof Error ? err.message : String(err)
        setSettled((s) => ({ ...s, path, error }))
      })
    return () => controller.abort()
  }, [path])

  const current = settled.path === path
  return {
    data: settled.data,
    error: current ? settled.error : undefined,
    loading: !current,
  }
}
