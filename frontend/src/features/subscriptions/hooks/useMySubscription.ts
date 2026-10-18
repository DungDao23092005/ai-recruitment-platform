import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ADMIN_SUBSCRIPTION_CHANGED_DOM_EVENT,
  STREAM_CONNECTED_DOM_EVENT,
  USER_SUBSCRIPTION_CHANGED_DOM_EVENT,
} from '@/hooks/useNotificationStream'
import type { AdminSubscriptionChangedDetail } from '@/hooks/useNotificationStream'
import { getMySubscription } from '@/api/subscriptions'
import type { Subscription } from '@/types/subscription'

export interface UseMySubscriptionResult {
  subscription: Subscription | null
  isLoading: boolean
  error: string | null
  refetch: () => void
}

// Coalesce bursts of realtime invalidations into a single network request.
const SILENT_REFRESH_DEBOUNCE_MS = 300

interface FetchOptions {
  // Silent refreshes never toggle the loading flag and never surface a
  // transient failure - they keep the last known UI state instead.
  silent: boolean
}

export function useMySubscription(): UseMySubscriptionResult {
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const isMountedRef = useRef(true)
  // Monotonic request generation: only the newest request may apply its result,
  // so a slow older response can never overwrite a newer one.
  const generationRef = useRef(0)
  // Track the newest manual (non-silent) request so its `finally` can safely
  // clear the loading flag even when a silent refresh supersedes it.
  const manualGenerationRef = useRef(0)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Latest known owner of the subscription, used to ignore admin invalidations
  // that clearly target a different user.
  const knownUserIdRef = useRef<string | null>(null)

  const fetchSubscription = useCallback(async (options: FetchOptions) => {
    const generation = ++generationRef.current
    let manualGeneration = manualGenerationRef.current

    if (!options.silent) {
      manualGeneration = ++manualGenerationRef.current
      setIsLoading(true)
      setError(null)
    }

    try {
      const data = await getMySubscription()

      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }

      if (data?.user_id) {
        knownUserIdRef.current = data.user_id
      }
      setSubscription(data ?? null)
      setError(null)
    } catch (err) {
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }

      if (options.silent) {
        // Keep the last known state and any existing error on transient failure.
        return
      }

      // Type-safe narrowing: cast to type with optional response property
      // This preserves runtime behavior while satisfying TypeScript
      const typedErr = err as { response?: { status?: number; message?: string } } | Error | undefined
      if (typedErr instanceof Error) {
        setError(typedErr.message)
      } else if (typedErr?.response?.status === 404) {
        setSubscription(null)
        setError(null)
      } else if (typedErr?.response?.message) {
        setError(typedErr.response.message)
      } else {
        setError('Unable to load subscription')
      }
    } finally {
      if (
        !options.silent &&
        isMountedRef.current &&
        manualGenerationRef.current === manualGeneration
      ) {
        setIsLoading(false)
      }
    }
  }, [])

  const refetch = useCallback(() => {
    void fetchSubscription({ silent: false })
  }, [fetchSubscription])

  const scheduleSilentRefresh = useCallback(() => {
    if (!isMountedRef.current) return

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null
      void fetchSubscription({ silent: true })
    }, SILENT_REFRESH_DEBOUNCE_MS)
  }, [fetchSubscription])

  useEffect(() => {
    isMountedRef.current = true
    void fetchSubscription({ silent: false })

    const handleUserSubscriptionChanged = () => {
      scheduleSilentRefresh()
    }

    const handleAdminSubscriptionChanged = (event: Event) => {
      const detail = (event as CustomEvent<AdminSubscriptionChangedDetail>).detail
      const eventUserId = detail?.user_id
      const knownUserId = knownUserIdRef.current
      // Wait for the next refresh to learn the user id when we don't know it yet
      // (e.g. a user without a subscription); otherwise ignore events that
      // target somebody else.
      if (eventUserId && knownUserId && eventUserId !== knownUserId) {
        return
      }
      scheduleSilentRefresh()
    }

    const handleStreamConnected = () => {
      scheduleSilentRefresh()
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        scheduleSilentRefresh()
      }
    }

    window.addEventListener(USER_SUBSCRIPTION_CHANGED_DOM_EVENT, handleUserSubscriptionChanged)
    window.addEventListener(ADMIN_SUBSCRIPTION_CHANGED_DOM_EVENT, handleAdminSubscriptionChanged)
    window.addEventListener(STREAM_CONNECTED_DOM_EVENT, handleStreamConnected)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      isMountedRef.current = false
      window.removeEventListener(USER_SUBSCRIPTION_CHANGED_DOM_EVENT, handleUserSubscriptionChanged)
      window.removeEventListener(ADMIN_SUBSCRIPTION_CHANGED_DOM_EVENT, handleAdminSubscriptionChanged)
      window.removeEventListener(STREAM_CONNECTED_DOM_EVENT, handleStreamConnected)
      document.removeEventListener('visibilitychange', handleVisibilityChange)

      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
        debounceTimerRef.current = null
      }
    }
  }, [fetchSubscription, scheduleSilentRefresh])

  return { subscription, isLoading, error, refetch }
}
