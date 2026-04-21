export type RoleKey = 'ADMINISTRADOR' | 'TRABAJADOR' | 'CLIENTE' | ''

export type AuthUser = {
  id: number
  username: string
  fullName: string
  email: string
  role: RoleKey
  dashboardPath: string
  isAdmin: boolean
  isWorker: boolean
  isClient: boolean
}

export type AuthResponse = {
  user: AuthUser
}

export type LoginPayload = {
  username: string
  password: string
}
