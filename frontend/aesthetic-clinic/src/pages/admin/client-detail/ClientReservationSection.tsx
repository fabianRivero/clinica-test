import { useState } from 'react'

import { ReservationModal } from '../components/ReservationModal'
import type { AdminReservationExtendedPayload } from '../../../types/admin'
import { DataState } from '../../../components/admin/DataState'
import { SectionCard } from '../../../components/admin/SectionCard'

interface ClientReservationSectionProps {
  effectiveOperationId: number | ''
  reservableOperations: any[]
  /** ID de la sucursal activa (provisto por el padre). */
  branchId: number | null
  onReserve: (payload: AdminReservationExtendedPayload) => Promise<void> | void
  /** Flag `isBooking` para deshabilitar el boton mientras la reserva corre. */
  isBookingKey: string | null
}

export function ClientReservationSection({
  reservableOperations,
  branchId,
  onReserve,
  isBookingKey,
}: ClientReservationSectionProps) {
  const [reservationModalOpen, setReservationModalOpen] = useState(false)

  if (!reservableOperations.length) {
    return (
      <SectionCard
        eyebrow="Reservas"
        title="Hacer reserva para este cliente"
        description="Agendar hora libre (Agenda abierta)."
      >
        <DataState
          title="Sin procedimientos en proceso"
          message="Este cliente no tiene tratamientos activos para nuevas reservas."
        />
      </SectionCard>
    )
  }

  return (
    <>
      <SectionCard
        eyebrow="Reservas"
        title="Hacer reserva para este cliente"
        description="Agendar hora libre (Agenda abierta)."
      >
        <p className="field__hint _mb-md">
          Captura los datos planificados (procedimiento, zona, especialistas y maquinaria
          esperada) y verifica la disponibilidad antes de confirmar.
        </p>
        <button
          type="button"
          className="button button--primary"
          onClick={() => setReservationModalOpen(true)}
          disabled={!branchId || isBookingKey !== null}
          data-testid="open-reservation-modal"
        >
          {isBookingKey ? 'Reservando...' : 'Reservar cita'}
        </button>
      </SectionCard>

      <ReservationModal
        isOpen={reservationModalOpen}
        onClose={() => setReservationModalOpen(false)}
        reservableOperations={reservableOperations}
        branchId={branchId ?? 0}
        onConfirm={async (payload) => {
          await onReserve(payload)
          setReservationModalOpen(false)
        }}
        isBooking={isBookingKey !== null}
      />
    </>
  )
}
