import { useCallback, useEffect, useRef, useState } from 'react'
import { getPlans } from '@/api/plans'
import type { PlanAudience, RecruitmentPlanRead } from '@/types/subscription'

export interface UsePlansResult {
  plans: RecruitmentPlanRead[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function usePlans(audience?: PlanAudience): UsePlansResult {
  const [plans, setPlans] = useState<RecruitmentPlanRead[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const generationRef = useRef(0)

  const refetch = useCallback(async () => {
    const generation = ++generationRef.current
    setIsLoading(true)
    setError(null)
    try {
      const data = await getPlans(audience)
      if (generationRef.current === generation) {
        setPlans(data)
      }
    } catch (err) {
      if (generationRef.current !== generation) return
      const message =
        err instanceof Error ? err.message : 'Unable to load plans'
      setError(message)
    } finally {
      if (generationRef.current === generation) {
        setIsLoading(false)
      }
    }
  }, [audience])

  useEffect(() => {
    void refetch()
  }, [refetch])

  return { plans, isLoading, error, refetch }
}
