import { useCallback, useEffect, useState } from 'react'
import { getMySubscription } from '@/api/subscriptions'
import type { Subscription } from '@/types/subscription'

export interface UseMySubscriptionResult {
  subscription: Subscription | null
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function useMySubscription(): UseMySubscriptionResult {
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getMySubscription()
      setSubscription(data ?? null)
    } catch (err) {
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
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refetch()
  }, [refetch])

  return { subscription, isLoading, error, refetch }
}