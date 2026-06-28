import { useCallback, useEffect, useState } from 'react'

type ApiState<T> = {
  data: T | null
  isLoading: boolean
  error: string | null
}

export function useApiResource<T>(loader: () => Promise<T>) {
  const [state, setState] = useState<ApiState<T>>({
    data: null,
    isLoading: true,
    error: null,
  })
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => {
    setReloadKey((current) => current + 1)
  }, [])

  useEffect(() => {
    let cancelled = false

    setState((prev) => ({
      // Keep the previous data visible while the next page loads so the
      // catalog list does not flash a loading skeleton (which causes the
      // browser to scroll the page back to the top because the list height
      // collapses momentarily). keepPreviousData pattern.
      data: prev.data,
      isLoading: true,
      error: null,
    }))

    loader()
      .then((data) => {
        if (!cancelled) {
          setState({
            data,
            isLoading: false,
            error: null,
          })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            data: null,
            isLoading: false,
            error: error instanceof Error ? error.message : 'No se pudo cargar la información.',
          })
        }
      })

    return () => {
      cancelled = true
    }
  }, [loader, reloadKey])

  return {
    ...state,
    reload,
  }
}
