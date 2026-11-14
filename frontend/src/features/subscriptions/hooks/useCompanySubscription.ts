import { useCallback, useEffect, useRef, useState } from 'react'
import { getCompanySubscription } from '@/api/subscriptions'
import { useOptionalWorkspace } from '@/contexts/WorkspaceContext'
import {
  STREAM_CONNECTED_DOM_EVENT,
  USER_SUBSCRIPTION_CHANGED_DOM_EVENT,
} from '@/hooks/useNotificationStream'
import type { Subscription } from '@/types/subscription'

export interface UseCompanySubscriptionResult {
  subscription: Subscription | null
  isLoading: boolean
  error: string | null
  refetch: () => void
}

const SILENT_REFRESH_DEBOUNCE_MS = 300

export function useCompanySubscription(
  enabled = true,
): UseCompanySubscriptionResult {
  const workspace = useOptionalWorkspace()
  const selectedCompanyId = workspace?.selectedCompanyId ?? null

  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [isLoading, setIsLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  const isMountedRef = useRef(true)
  const generationRef = useRef(0)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchSubscription = useCallback(
    async (silent: boolean) => {
      const generation = ++generationRef.current
      if (!silent) {
        setIsLoading(true)
        setError(null)
      }

      try {
        const data = await getCompanySubscription()
        if (!isMountedRef.current || generationRef.current !== generation) {
          return
        }
        setSubscription(data ?? null)
        setError(null)
      } catch (err) {
        if (!isMountedRef.current || generationRef.current !== generation) {
          return
        }
        if (silent) {
          return
        }
        const message =
          err instanceof Error
            ? err.message
            : 'Không thể tải thông tin gói dịch vụ.'
        setError(message)
      } finally {
        if (!silent && isMountedRef.current && generationRef.current === generation) {
          setIsLoading(false)
        }
      }
    },
    [],
  )

  const refetch = useCallback(() => {
    void fetchSubscription(false)
  }, [fetchSubscription])

  const scheduleSilentRefresh = useCallback(() => {
    if (!isMountedRef.current) return
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null
      void fetchSubscription(true)
    }, SILENT_REFRESH_DEBOUNCE_MS)
  }, [fetchSubscription])

  useEffect(() => {
    isMountedRef.current = true

    if (!enabled) {
      generationRef.current += 1
      setSubscription(null)
      setIsLoading(false)
      setError(null)
      return () => {
        isMountedRef.current = false
      }
    }

    void fetchSubscription(false)

    const handleChanged = () => scheduleSilentRefresh()
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        scheduleSilentRefresh()
      }
    }

    window.addEventListener(USER_SUBSCRIPTION_CHANGED_DOM_EVENT, handleChanged)
    window.addEventListener(STREAM_CONNECTED_DOM_EVENT, handleChanged)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      isMountedRef.current = false
      window.removeEventListener(USER_SUBSCRIPTION_CHANGED_DOM_EVENT, handleChanged)
      window.removeEventListener(STREAM_CONNECTED_DOM_EVENT, handleChanged)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
        debounceTimerRef.current = null
      }
    }
  }, [enabled, fetchSubscription, scheduleSilentRefresh, selectedCompanyId])

  return { subscription, isLoading, error, refetch }
}
