import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { getAdminBranches } from '../services/api/admin'
import { setActiveBranchId } from '../services/api/activeBranch'
import { useAuth } from './AuthProvider'
import type { AdminBranch } from '../types/admin'

type BranchContextValue = {
  branches: AdminBranch[]
  activeBranch: AdminBranch | null
  isLoading: boolean
  error: string | null
  isBranchLocked: boolean
  setActiveBranch: (branchId: number) => void
  refreshBranches: () => Promise<void>
}

const BranchContext = createContext<BranchContextValue | null>(null)

export function BranchProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [branches, setBranches] = useState<AdminBranch[]>([])
  const [activeBranch, setActiveBranchState] = useState<AdminBranch | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Si el usuario es admin de sucursal, su sucursal está fija
  const isBranchLocked = Boolean(user && !user.isMainAdmin && user.branchId)
  const lockedBranchId = isBranchLocked ? user!.branchId : null

  // Sincronizar branchId activo con el store compartido para las funciones API
  useEffect(() => {
    setActiveBranchId(activeBranch?.id ?? null)
  }, [activeBranch])

  const fetchBranches = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await getAdminBranches()
      setBranches(response.branches)

      if (response.branches.length > 0) {
        if (lockedBranchId) {
          // Admin de sucursal: fijar a su sucursal
          const locked = response.branches.find((b) => b.id === lockedBranchId)
          setActiveBranchState(locked || response.branches[0])
        } else if (!activeBranch) {
          const principal = response.branches.find((b) => b.es_principal)
          setActiveBranchState(principal || response.branches[0])
        } else {
          const stillExists = response.branches.find((b) => b.id === activeBranch.id)
          if (!stillExists) {
            const principal = response.branches.find((b) => b.es_principal)
            setActiveBranchState(principal || response.branches[0])
          } else {
             setActiveBranchState(stillExists)
          }
        }
      } else {
        setActiveBranchState(null)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar sucursales')
    } finally {
      setIsLoading(false)
    }
  }, [activeBranch, lockedBranchId])

  useEffect(() => {
    void fetchBranches()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setActiveBranch = useCallback(
    (branchId: number) => {
      // No permitir cambio si la sucursal está fija
      if (isBranchLocked) return
      const branch = branches.find((b) => b.id === branchId)
      if (branch) {
        setActiveBranchState(branch)
      }
    },
    [branches, isBranchLocked],
  )

  return (
    <BranchContext.Provider
      value={{
        branches,
        activeBranch,
        isLoading,
        error,
        isBranchLocked,
        setActiveBranch,
        refreshBranches: fetchBranches,
      }}
    >
      {children}
    </BranchContext.Provider>
  )
}

export function useBranchContext() {
  const context = useContext(BranchContext)
  if (!context) {
    throw new Error('useBranchContext must be used within a BranchProvider')
  }
  return context
}
