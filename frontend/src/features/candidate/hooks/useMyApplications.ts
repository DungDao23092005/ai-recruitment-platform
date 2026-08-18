import { useCallback, useEffect, useState } from 'react'
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

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getMyApplications({
        skip: 0,
        limit: APPLICATIONS_PAGE_SIZE,
      })
      setApplications(data)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
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