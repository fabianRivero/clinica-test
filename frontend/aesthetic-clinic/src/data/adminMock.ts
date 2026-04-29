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
    delta: '3 pendientes de biometria',
    tone: 'danger',
  },
]

export const adminAlerts: AdminAlert[] = [
  {
    id: 'alert-1',
    title: 'Comprobantes sin revisar por mas de 24 horas',
    description:
      'Hay 5 pagos pendientes que ya impactan vencimientos y bloqueo de reservas.',
    severity: 'high',
    action: 'Priorizar validacion',
  },
  {
    id: 'alert-2',
    title: 'Operaciones con sesiones agotadas',
    description:
      'Tres pacientes no tienen sesiones disponibles y siguen intentando reservar.',
    severity: 'medium',
    action: 'Revisar ampliacion',
  },
  {
    id: 'alert-3',
    title: 'Catalogo clinico desactualizado',
    description:
      'El procedimiento de manchas todavia no tiene las nuevas respuestas clinicas publicadas.',
    severity: 'low',
    action: 'Actualizar catalogo',
  },
]

export const paymentQueue: VerificationPayment[] = [
  {
    id: 'PAY-1042',
    rawId: 1042,
    patient: 'Maria Fernanda Rojas',
    operation: 'Depilacion laser full body',
    amount: 'Bs 850',
    submittedAt: 'Hoy · 08:40',
    bank: 'BCP',
    status: 'pendiente',
  },
  {
    id: 'PAY-1038',
    rawId: 1038,
    patient: 'Luciana Arteaga',
    operation: 'Borrado de tatuaje antebrazo',
    amount: 'Bs 420',
    submittedAt: 'Ayer · 18:15',
    bank: 'Banco Union',
    status: 'observado',
  },
  {
    id: 'PAY-1035',
    rawId: 1035,
    patient: 'Valeria Cuellar',
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
    procedure: 'Depilacion axilas',
    specialist: 'Dra. Lucia Suarez',
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
    patient: 'Monica Ibanez',
    procedure: 'Control manchas',
    specialist: 'Dra. Lucia Suarez',
    status: 'programada',
  },
]

export const prospectPipeline: ProspectLead[] = [
  {
    id: 'PRO-221',
    name: 'Paola Antelo',
    phone: '72100122',
    interest: 'Depilacion pierna completa',
    registeredBy: 'Recepcion',
    stage: 'seguimiento',
  },
  {
    id: 'PRO-219',
    name: 'Angela Rocha',
    phone: '76533456',
    interest: 'Manchas faciales',
    registeredBy: 'Asesora Luz',
    stage: 'propuesta',
  },
  {
    id: 'PRO-217',
    name: 'Natalia Mendez',
    phone: '69912344',
    interest: 'Borrado de tatuaje',
    registeredBy: 'Recepcion',
    stage: 'nuevo',
  },
]

export const highlightedOperations: OperationCardData[] = [
  {
    id: 'OP-553',
    rawId: 553,
    patient: 'Maria Fernanda Rojas',
    procedure: 'Depilacion laser full body',
    specialist: 'Dra. Lucia Suarez',
    sessions: '8 total · 5 confirmadas · 1 reservada',
    nextAppointment: '22 abr · 16:00',
    quotaStatus: '1 cuota pendiente',
  },
  {
    id: 'OP-547',
    rawId: 547,
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
    name: 'Procedimientos esteticos',
    count: 3,
    note: 'Depilacion, manchas y tatuajes activos',
  },
  {
    id: 'cat-2',
    name: 'Campos clinicos',
    count: 24,
    note: '2 respuestas pendientes de revision',
  },
  {
    id: 'cat-3',
    name: 'Especialidades',
    count: 5,
    note: 'Sin conflictos de nomenclatura',
  },
  {
    id: 'cat-4',
    name: 'Patologias cutaneas',
    count: 13,
    note: 'Ultima actualizacion hace 7 dias',
  },
]

export const staffCapacity: StaffCapacityItem[] = [
  {
    id: 'stf-1',
    rawId: 1,
    specialist: 'Dra. Lucia Suarez',
    specialty: 'Laser dermatologico',
    specialtyIds: [1],
    load: 84,
    pendingValidations: 1,
    username: 'lucia.suarez',
    email: 'lucia.suarez@clinica.test',
    primerNombre: 'Lucia',
    segundoNombre: '',
    apellidoPaterno: 'Suarez',
    apellidoMaterno: '',
    ci: '7845123',
    phone: '70000001',
    status: 'Activo',
    isActive: true,
    activeOperations: 6,
    upcomingAppointments: 4,
    observations: 'Seguimiento de validaciones de agenda.',
  },
  {
    id: 'stf-2',
    rawId: 2,
    specialist: 'Dr. Diego Roca',
    specialty: 'Borrado de tatuajes',
    specialtyIds: [2],
    load: 68,
    pendingValidations: 2,
    username: 'diego.roca',
    email: 'diego.roca@clinica.test',
    primerNombre: 'Diego',
    segundoNombre: '',
    apellidoPaterno: 'Roca',
    apellidoMaterno: '',
    ci: '6123456',
    phone: '70000002',
    status: 'Activo',
    isActive: true,
    activeOperations: 5,
    upcomingAppointments: 3,
    observations: 'Tiene comprobantes pendientes de revisar.',
  },
  {
    id: 'stf-3',
    rawId: 3,
    specialist: 'Lic. Sofia Mendez',
    specialty: 'Evaluacion estetica',
    specialtyIds: [3],
    load: 53,
    pendingValidations: 0,
    username: 'sofia.mendez',
    email: 'sofia.mendez@clinica.test',
    primerNombre: 'Sofia',
    segundoNombre: '',
    apellidoPaterno: 'Mendez',
    apellidoMaterno: '',
    ci: '5987654',
    phone: '70000003',
    status: 'Activo',
    isActive: true,
    activeOperations: 3,
    upcomingAppointments: 2,
    observations: '',
  },
]
