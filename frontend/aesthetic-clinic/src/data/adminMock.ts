import type {
  AdminAlert,
  AdminMetric,
  AgendaItem,
  CatalogHealthItem,
  OperationCardData,
  ProspectLead,
  StaffCapacityItem,
  VerificationPayment,
} from '../types/admin'

export const adminMetrics: AdminMetric[] = [
  {
    id: 'payments',
    label: 'Pagos por verificar',
    value: '14',
    delta: '+4 hoy',
    tone: 'warning',
  },
  {
    id: 'operations',
    label: 'Tratamientos activos',
    value: '126',
    delta: '+9 este mes',
    tone: 'primary',
  },
  {
    id: 'prospects',
    label: 'Prospectos en seguimiento',
    value: '38',
    delta: '62% con respuesta',
    tone: 'success',
  },
  {
    id: 'appointments',
    label: 'Citas hoy',
    value: '21',
    delta: '3 pendientes de biometría',
    tone: 'danger',
  },
]

export const adminAlerts: AdminAlert[] = [
  {
    id: 'alert-1',
    title: 'Comprobantes sin revisar por más de 24 horas',
    description:
      'Hay 5 pagos pendientes que ya impactan vencimientos y bloqueo de reservas.',
    severity: 'high',
    action: 'Priorizar validación',
  },
  {
    id: 'alert-2',
    title: 'Operaciones con sesiones agotadas',
    description:
      'Tres pacientes no tienen sesiones disponibles y siguen intentando reservar.',
    severity: 'medium',
    action: 'Revisar ampliación',
  },
  {
    id: 'alert-3',
    title: 'Catálogo clínico desactualizado',
    description:
      'El procedimiento de manchas todavía no tiene las nuevas respuestas clínicas publicadas.',
    severity: 'low',
    action: 'Actualizar catálogo',
  },
]

export const paymentQueue: VerificationPayment[] = [
  {
    id: 'PAY-1042',
    patient: 'María Fernanda Rojas',
    operation: 'Depilación láser full body',
    amount: 'Bs 850',
    submittedAt: 'Hoy · 08:40',
    bank: 'BCP',
    status: 'pendiente',
  },
  {
    id: 'PAY-1038',
    patient: 'Luciana Arteaga',
    operation: 'Borrado de tatuaje antebrazo',
    amount: 'Bs 420',
    submittedAt: 'Ayer · 18:15',
    bank: 'Banco Unión',
    status: 'observado',
  },
  {
    id: 'PAY-1035',
    patient: 'Valeria Cuéllar',
    operation: 'Tratamiento de manchas faciales',
    amount: 'Bs 600',
    submittedAt: 'Ayer · 11:12',
    bank: 'Mercantil',
    status: 'aprobado',
  },
]

export const todayAgenda: AgendaItem[] = [
  {
    id: 'CIT-883',
    time: '09:00',
    patient: 'Camila Soruco',
    procedure: 'Depilación axilas',
    specialist: 'Dra. Lucía Suárez',
    status: 'confirmada',
  },
  {
    id: 'CIT-884',
    time: '10:30',
    patient: 'Jimena Vaca',
    procedure: 'Borrado de tatuaje',
    specialist: 'Dr. Diego Roca',
    status: 'biometria',
  },
  {
    id: 'CIT-885',
    time: '11:45',
    patient: 'Mónica Ibáñez',
    procedure: 'Control manchas',
    specialist: 'Dra. Lucía Suárez',
    status: 'programada',
  },
]

export const prospectPipeline: ProspectLead[] = [
  {
    id: 'PRO-221',
    name: 'Paola Antelo',
    phone: '72100122',
    interest: 'Depilación pierna completa',
    registeredBy: 'Recepción',
    stage: 'seguimiento',
  },
  {
    id: 'PRO-219',
    name: 'Ángela Rocha',
    phone: '76533456',
    interest: 'Manchas faciales',
    registeredBy: 'Asesora Luz',
    stage: 'propuesta',
  },
  {
    id: 'PRO-217',
    name: 'Natalia Méndez',
    phone: '69912344',
    interest: 'Borrado de tatuaje',
    registeredBy: 'Recepción',
    stage: 'nuevo',
  },
]

export const highlightedOperations: OperationCardData[] = [
  {
    id: 'OP-553',
    patient: 'María Fernanda Rojas',
    procedure: 'Depilación láser full body',
    specialist: 'Dra. Lucía Suárez',
    sessions: '8 total · 5 confirmadas · 1 reservada',
    nextAppointment: '22 abr · 16:00',
    quotaStatus: '1 cuota pendiente',
  },
  {
    id: 'OP-547',
    patient: 'Luciana Arteaga',
    procedure: 'Borrado de tatuaje antebrazo',
    specialist: 'Dr. Diego Roca',
    sessions: '6 total · 2 confirmadas · 1 reservada',
    nextAppointment: '20 abr · 10:30',
    quotaStatus: 'Pago observado',
  },
]

export const catalogHealth: CatalogHealthItem[] = [
  {
    id: 'cat-1',
    name: 'Procedimientos estéticos',
    count: 3,
    note: 'Depilación, manchas y tatuajes activos',
  },
  {
    id: 'cat-2',
    name: 'Campos clínicos',
    count: 24,
    note: '2 respuestas pendientes de revisión',
  },
  {
    id: 'cat-3',
    name: 'Especialidades',
    count: 5,
    note: 'Sin conflictos de nomenclatura',
  },
  {
    id: 'cat-4',
    name: 'Patologías cutáneas',
    count: 13,
    note: 'Última actualización hace 7 días',
  },
]

export const staffCapacity: StaffCapacityItem[] = [
  {
    id: 'stf-1',
    specialist: 'Dra. Lucía Suárez',
    specialty: 'Láser dermatológico',
    load: 84,
    pendingValidations: 1,
  },
  {
    id: 'stf-2',
    specialist: 'Dr. Diego Roca',
    specialty: 'Borrado de tatuajes',
    load: 68,
    pendingValidations: 2,
  },
  {
    id: 'stf-3',
    specialist: 'Lic. Sofía Méndez',
    specialty: 'Evaluación estética',
    load: 53,
    pendingValidations: 0,
  },
]
