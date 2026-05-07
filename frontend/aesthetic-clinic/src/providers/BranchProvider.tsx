import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { getAdminBranches } from '../services/api/admin'
import type { AdminBranch } from '../types/admin'

type BranchContextValue = {
  branches: AdminBranch[]
  activeBranch: AdminBranch | null
  isLoading: boolean
  error: string | null
  setActiveBranch: (branchId: number) => void
  refreshBranches: () => Promise<void>
}

const BranchContext = createContext<BranchContextValue | null>(null)

export function BranchProvider({ children }: { children: ReactNode }) {
  const [branches, setBranches] = useState<AdminBranch[]>([])
  const [activeBranch, setActiveBranchState] = useState<AdminBranch | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchBranches = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await getAdminBranches()
      setBranches(response.branches)

      if (response.branches.length > 0) {
        // If no active branch is set yet, default to the principal one or the first one
        if (!activeBranch) {
          const principal = response.branches.find((b) => b.es_principal)
          setActiveBranchState(principal || response.branches[0])
        } else {
          // If there is an active branch, make sure it still exists in the fetched list
          const stillExists = response.branches.find((b) => b.id === activeBranch.id)
          if (!stillExists) {
            const principal = response.branches.find((b) => b.es_principal)
            setActiveBranchState(principal || response.branches[0])
          } else {
             // Update references to match fetched
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
  }, [activeBranch])

  useEffect(() => {
    void fetchBranches()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setActiveBranch = useCallback(
    (branchId: number) => {
      const branch = branches.find((b) => b.id === branchId)
      if (branch) {
        setActiveBranchState(branch)
      }
    },
    [branches],
  )

  return (
    <BranchContext.Provider
      value={{
        branches,
        activeBranch,
        isLoading,
        error,
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
