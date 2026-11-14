import { useCallback, useEffect, useRef, useState } from 'react'
import { getCandidateEntitlementSummary } from '@/api/subscriptions'
import {
  STREAM_CONNECTED_DOM_EVENT,
  USER_SUBSCRIPTION_CHANGED_DOM_EVENT,
} from '@/hooks/useNotificationStream'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { CandidateEntitlementSummary } from '@/types/subscription'

export interface UseCandidateEntitlementResult {
  entitlement: CandidateEntitlementSummary | null
  isLoading: boolean
  error: string | null
  refetch: () => void
}

const SILENT_REFRESH_DEBOUNCE_MS = 300

export function useCandidateEntitlement(
  enabled = true,
): UseCandidateEntitlementResult {
  const [entitlement, setEntitlement] =
    useState<CandidateEntitlementSummary | null>(null)
  const [isLoading, setIsLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  const isMountedRef = useRef(true)
  const generationRef = useRef(0)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchEntitlement = useCallback(async (silent: boolean) => {
    const generation = ++generationRef.current
    if (!silent) {
      setIsLoading(true)
      setError(null)
    }

    try {
      const data = await getCandidateEntitlementSummary()
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }
      setEntitlement(data)
      setError(null)
    } catch (err) {
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }
      if (silent) return
      setError(getFriendlyErrorMessage(err))
    } finally {
      if (
        !silent &&
        isMountedRef.current &&
        generationRef.current === generation
      ) {
        setIsLoading(false)
      }
    }
  }, [])

  const refetch = useCallback(() => {
    void fetchEntitlement(false)
  }, [fetchEntitlement])

  const scheduleSilentRefresh = useCallback(() => {
    if (!isMountedRef.current) return
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null
      void fetchEntitlement(true)
    }, SILENT_REFRESH_DEBOUNCE_MS)
  }, [fetchEntitlement])

  useEffect(() => {
    isMountedRef.current = true

    if (!enabled) {
      generationRef.current += 1
      setEntitlement(null)
      setIsLoading(false)
      setError(null)
      return () => {
        isMountedRef.current = false
      }
    }

    void fetchEntitlement(false)

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
      window.removeEventListener(
        USER_SUBSCRIPTION_CHANGED_DOM_EVENT,
        handleChanged,
      )
      window.removeEventListener(STREAM_CONNECTED_DOM_EVENT, handleChanged)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
        debounceTimerRef.current = null
      }
    }
  }, [enabled, fetchEntitlement, scheduleSilentRefresh])

  return { entitlement, isLoading, error, refetch }
}
