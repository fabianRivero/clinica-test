// API wrappers for the specialist-only endpoints.

import type { MisCitasResponse } from '../../types/admin'

import { requestJson } from './apiClient'


export function getMyAppointments(): Promise<MisCitasResponse> {
  return requestJson<MisCitasResponse>('/api/especialista/mis-citas/')
}