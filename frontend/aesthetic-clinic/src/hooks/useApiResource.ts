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

    setState({
      data: null,
      isLoading: true,
      error: null,
    })

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
            error: error instanceof Error ? error.message : 'No se pudo cargar la informacion.',
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
