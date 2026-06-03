import { useCallback, useEffect, useState } from 'react'
import type { WeekAvailability } from '../types/worker'

type UseSpecialistAvailabilityResult = {
  loading: boolean
  availability: WeekAvailability | null
  error: string | null
  refetch: () => void
}

export function useSpecialistAvailability(): UseSpecialistAvailabilityResult {
  const [availability, setAvailability] = useState<WeekAvailability | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)

  const refetch = useCallback(() => {
    setRetryKey((k) => k + 1)
  }, [])

  useEffect(() => {
    let cancelled = false

    // eslint-disable-next-line react-hooks/set-state-in-effect -- matches useApiResource pattern
    setLoading(true)
    setError(null)

    const url = '/api/admin/trabajador/disponibilidad/'

    fetch(url, { credentials: 'include' })
      .then((res) => {
        if (!cancelled) {
          if (res.status === 403) {
            setError('No tienes acceso')
            setLoading(false)
            return
          }
          if (!res.ok) {
            setError('Error cargando disponibilidad')
            setLoading(false)
            return
          }
          return res.json()
        }
      })
      .then((data: WeekAvailability | undefined) => {
        if (!cancelled && data) {
          // Empty state: no shifts and no blocks in all days
          const allEmpty = data.days.every(
            (day) => day.shifts.length === 0 && day.blocks.length === 0,
          )
          if (allEmpty) {
            setError('Sin agenda configurada')
          }
          setAvailability(data)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('Error cargando disponibilidad')
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [retryKey])

  return { loading, availability, error, refetch }
}