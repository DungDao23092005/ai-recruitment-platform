import { useCallback, useEffect, useRef, useState } from 'react'
import { getCandidateUsages } from '@/api/subscriptions'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type {
  CandidateUsageHistoryResponse,
  CandidateUsageQueryParams,
} from '@/types/subscription'

export interface UseCandidateUsageHistoryResult {
  data: CandidateUsageHistoryResponse | null
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function useCandidateUsageHistory(
  params: CandidateUsageQueryParams,
  enabled = true,
): UseCandidateUsageHistoryResult {
  const [data, setData] = useState<CandidateUsageHistoryResponse | null>(null)
  const [isLoading, setIsLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  const generationRef = useRef(0)
  const isMountedRef = useRef(true)

  const paramsKey = JSON.stringify(params)

  const fetchUsages = useCallback(async () => {
    const generation = ++generationRef.current
    setIsLoading(true)
    setError(null)
    try {
      const response = await getCandidateUsages(
        JSON.parse(paramsKey) as CandidateUsageQueryParams,
      )
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }
      setData(response)
    } catch (err) {
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }
      setError(getFriendlyErrorMessage(err))
    } finally {
      if (isMountedRef.current && generationRef.current === generation) {
        setIsLoading(false)
      }
    }
  }, [paramsKey])

  const refetch = useCallback(() => {
    void fetchUsages()
  }, [fetchUsages])

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  useEffect(() => {
    if (!enabled) {
      generationRef.current += 1
      setData(null)
      setIsLoading(false)
      setError(null)
      return
    }
    void fetchUsages()
  }, [enabled, fetchUsages])

  return { data, isLoading, error, refetch }
}
