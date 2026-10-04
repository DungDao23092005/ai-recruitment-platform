import { useCallback, useEffect, useState } from 'react'
import { getPlans } from '@/api/plans'
import type { RecruitmentPlanRead } from '@/types/subscription'

export interface UsePlansResult {
  plans: RecruitmentPlanRead[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function usePlans(): UsePlansResult {
  const [plans, setPlans] = useState<RecruitmentPlanRead[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getPlans()
      setPlans(data)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unable to load plans'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refetch()
  }, [refetch])

  return { plans, isLoading, error, refetch }
}