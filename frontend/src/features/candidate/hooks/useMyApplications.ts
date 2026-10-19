import { useCallback, useEffect, useRef, useState } from 'react'
import { getMyApplications } from '@/api/applications'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type {
  ApplicationStatus,
  ApplicationWithJob,
} from '@/types/application'

export const APPLICATIONS_PAGE_SIZE = 10

export interface UseMyApplicationsResult {
  applications: ApplicationWithJob[]
  isLoading: boolean
  error: string | null
  refresh: () => void
  updateStatus: (applicationId: string, status: ApplicationStatus) => void
}

export function useMyApplications(): UseMyApplicationsResult {
  const [applications, setApplications] = useState<ApplicationWithJob[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    setIsLoading(true)
    setError(null)
    try {
      const data = await getMyApplications({
        skip: 0,
        limit: APPLICATIONS_PAGE_SIZE,
      })
      if (requestIdRef.current === requestId) {
        setApplications(data)
      }
    } catch (err) {
      if (requestIdRef.current === requestId) {
        setError(getFriendlyErrorMessage(err))
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setIsLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const updateStatus = useCallback(
    (applicationId: string, status: ApplicationStatus) => {
      setApplications((prev) =>
        prev.map((application) =>
          application.id === applicationId
            ? { ...application, status }
            : application,
        ),
      )
    },
    [],
  )

  return { applications, isLoading, error, refresh: load, updateStatus }
}