export type RoleKey = 'ADMINISTRADOR' | 'TRABAJADOR' | 'CLIENTE' | ''

export type AuthUser = {
  id: number
  username: string
  fullName: string
  email: string
  telefono: string
  role: RoleKey
  dashboardPath: string
  isAdmin: boolean
  isMainAdmin: boolean
  isSuperuser?: boolean
  isWorker: boolean
  isClient: boolean
  branchId: number | null
  branchName: string
  /**
   * Set by the admin-assisted password reset flow. When true, the
   * user must pick a new password before accessing any feature
   * besides the change-password modal.
   */
  mustChangePassword: boolean
}

export type AuthResponse = {
  user: AuthUser
}

export type LoginPayload = {
  username: string
  password: string
}

export type ProfileUpdatePayload = {
  username?: string
  email?: string
  telefono?: string
  password?: string
}
