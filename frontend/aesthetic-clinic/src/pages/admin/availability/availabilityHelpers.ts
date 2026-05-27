export function buildEmptyHabitualForm(branchId: number) {
  return {
    specialistId: null as number | null,
    specialistIds: [] as number[],
    branchId: branchId,
    startDate: '',
    endDate: '',
    weekdayCodes: [] as number[],
    startTime: '',
    endTime: '',
    detail: '',
  }
}

export function buildEmptyExceptionForm(branchId: number) {
  return {
    specialistIds: [] as number[],
    branchId: branchId,
    type: 'BLOQUEAR' as 'AGREGAR' | 'BLOQUEAR',
    dateInput: '',
    dates: [] as string[],
    useDateRange: false,
    rangeStartDate: '',
    rangeEndDate: '',
    rangeWeekdayCodes: [] as number[],
    startTime: '08:00',
    endTime: '18:00',
    detail: '',
    isWholeDay: true,
  }
}

export function toggleSelection(current: number[], value: number) {
  return current.includes(value)
    ? current.filter((item) => item !== value)
    : [...current, value].sort((a, b) => a - b)
}

export type HabitualFormType = ReturnType<typeof buildEmptyHabitualForm>
export type ExceptionFormType = ReturnType<typeof buildEmptyExceptionForm>

export interface SpecialistOption {
  id: number
  label: string
}

export interface WeekdayOption {
  value: number
  label: string
}