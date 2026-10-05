import apiClient from '@/api/client'
import type { RecruitmentPlanRead } from '@/types/subscription'

export async function getPlans(): Promise<RecruitmentPlanRead[]> {
  return apiClient.get<RecruitmentPlanRead, RecruitmentPlanRead[]>('/plans')
}

export async function getPlan(planId: string): Promise<RecruitmentPlanRead> {
  return apiClient.get<RecruitmentPlanRead, RecruitmentPlanRead>(`/plans/${planId}`)
}