import {
  createContext,
  type PropsWithChildren,
  useContext,
  useEffect,
  useState,
} from 'react'

import { getSessionUser, loginUser, logoutUser } from '../services/api/auth'
import type { AuthUser, LoginPayload } from '../types/auth'

type AuthContextValue = {
  user: AuthUser | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (payload: LoginPayload) => Promise<AuthUser>
  logout: () => Promise<void>
  refreshSession: () => Promise<AuthUser | null>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let isMounted = true

    async function bootstrapSession() {
      try {
        const sessionUser = await getSessionUser()
        if (isMounted) {
          setUser(sessionUser)
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    void bootstrapSession()

    return () => {
      isMounted = false
    }
  }, [])

  async function refreshSession() {
    const sessionUser = await getSessionUser()
    setUser(sessionUser)
    return sessionUser
  }

  async function login(payload: LoginPayload) {
    const response = await loginUser(payload)
    setUser(response.user)
    return response.user
  }

  async function logout() {
    await logoutUser()
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: Boolean(user),
        login,
        logout,
        refreshSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)

  if (!context) {
    throw new Error('useAuth debe usarse dentro de AuthProvider.')
  }

  return context
}
