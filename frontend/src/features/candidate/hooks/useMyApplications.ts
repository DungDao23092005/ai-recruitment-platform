import { useCallback, useEffect, useRef, useState } from 'react'
import { getMyApplications } from '@/api/applications'
import {
  CANDIDATE_PIPELINE_UPDATED_DOM_EVENT,
  STREAM_CONNECTED_DOM_EVENT,
} from '@/hooks/useNotificationStream'
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

  const load = useCallback(async (silent = false) => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    if (!silent) {
      setIsLoading(true)
      setError(null)
    }
    try {
      const data = await getMyApplications({
        skip: 0,
        limit: APPLICATIONS_PAGE_SIZE,
      })
      if (requestIdRef.current === requestId) {
        setApplications(data)
        setError(null)
      }
    } catch (err) {
      if (requestIdRef.current === requestId && !silent) {
        setError(getFriendlyErrorMessage(err))
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setIsLoading(false)
      }
    }
  }, [])

  const refresh = useCallback(() => {
    void load(true)
  }, [load])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    return () => {
      requestIdRef.current += 1
    }
  }, [])

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null

    const scheduleRefresh = () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = null
        refresh()
      }, 250)
    }

    const handlePipelineUpdated = (event: Event) => {
      const detail = (
        event as CustomEvent<{ application_id?: string } | undefined>
      ).detail
      if (!detail || typeof detail !== 'object') return
      scheduleRefresh()
    }

    const handleStreamConnected = () => scheduleRefresh()
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') scheduleRefresh()
    }

    window.addEventListener(
      CANDIDATE_PIPELINE_UPDATED_DOM_EVENT,
      handlePipelineUpdated,
    )
    window.addEventListener(STREAM_CONNECTED_DOM_EVENT, handleStreamConnected)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      if (timer) clearTimeout(timer)
      window.removeEventListener(
        CANDIDATE_PIPELINE_UPDATED_DOM_EVENT,
        handlePipelineUpdated,
      )
      window.removeEventListener(
        STREAM_CONNECTED_DOM_EVENT,
        handleStreamConnected,
      )
      document.removeEventListener(
        'visibilitychange',
        handleVisibilityChange,
      )
    }
  }, [refresh])

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

  return { applications, isLoading, error, refresh, updateStatus }
}