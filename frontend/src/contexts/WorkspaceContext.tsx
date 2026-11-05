import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  clearWorkspaceCompanyId,
  getStoredWorkspaceCompanyId,
  storeWorkspaceCompanyId,
} from '@/api/client'
import { getWorkspaces } from '@/api/workspaces'
import { useAuth } from '@/contexts/AuthContext'
import type { Workspace } from '@/types/workspace'

interface WorkspaceContextValue {
  workspaces: Workspace[]
  selectedCompanyId: string | null
  selectedWorkspace: Workspace | null
  isLoading: boolean
  error: string | null
  selectWorkspace: (companyId: string | null) => void
  refreshWorkspaces: () => Promise<Workspace[]>
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(
  undefined,
)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { currentUser } = useAuth()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(
    getStoredWorkspaceCompanyId(),
  )
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const applySelection = useCallback((companyId: string | null) => {
    setSelectedCompanyId(companyId)
    if (companyId) {
      storeWorkspaceCompanyId(companyId)
    } else {
      clearWorkspaceCompanyId()
    }
  }, [])

  const loadWorkspaces = useCallback(async (): Promise<Workspace[]> => {
    if (!currentUser || currentUser.role === 'candidate') {
      setWorkspaces([])
      applySelection(null)
      return []
    }

    setIsLoading(true)
    setError(null)
    try {
      const items = await getWorkspaces()
      setWorkspaces(items)

      const stored = getStoredWorkspaceCompanyId()
      const storedValid = items.some(
        (workspace) => workspace.company_id === stored,
      )
      if (storedValid) {
        setSelectedCompanyId(stored)
        return items
      }

      if (currentUser.role === 'recruiter' && items.length > 0) {
        applySelection(items[0].company_id)
      } else {
        applySelection(null)
      }
      return items
    } catch (loadError) {
      console.warn('Unable to load company workspaces:', loadError)
      setWorkspaces([])
      setError('Không thể tải danh sách công ty làm việc.')
      return []
    } finally {
      setIsLoading(false)
    }
  }, [applySelection, currentUser])

  useEffect(() => {
    void loadWorkspaces()
  }, [loadWorkspaces])

  const selectedWorkspace = useMemo(
    () =>
      workspaces.find(
        (workspace) => workspace.company_id === selectedCompanyId,
      ) ?? null,
    [selectedCompanyId, workspaces],
  )

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      workspaces,
      selectedCompanyId,
      selectedWorkspace,
      isLoading,
      error,
      selectWorkspace: applySelection,
      refreshWorkspaces: loadWorkspaces,
    }),
    [
      applySelection,
      error,
      isLoading,
      loadWorkspaces,
      selectedCompanyId,
      selectedWorkspace,
      workspaces,
    ],
  )

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext)
  if (context === undefined) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider')
  }
  return context
}
