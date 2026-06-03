export type Shift = {
  start: string
  end: string
  source: 'HABITUAL' | 'EXCEPTION_AGREGAR'
}

export type Block = {
  reason: string
  type: 'BLOQUEAR'
}

export type DayAvailability = {
  date: string
  weekdayLabel: string
  weekdayCode: number
  branchName: string
  shifts: Shift[]
  blocks: Block[]
}

export type WeekAvailability = {
  weekStart: string
  weekEnd: string
  days: DayAvailability[]
}