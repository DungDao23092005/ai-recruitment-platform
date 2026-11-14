import apiClient from '@/api/client'
import type { PlanAudience, RecruitmentPlanRead } from '@/types/subscription'

export async function getPlans(
  audience?: PlanAudience,
): Promise<RecruitmentPlanRead[]> {
  if (audience) {
    return apiClient.get<RecruitmentPlanRead[], RecruitmentPlanRead[]>('/plans', {
      params: { audience },
    })
  }
  return apiClient.get<RecruitmentPlanRead, RecruitmentPlanRead[]>('/plans')
}

export async function getPlan(planId: string): Promise<RecruitmentPlanRead> {
  return apiClient.get<RecruitmentPlanRead, RecruitmentPlanRead>(`/plans/${planId}`)
}
