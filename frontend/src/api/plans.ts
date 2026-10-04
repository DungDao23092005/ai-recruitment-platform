import apiClient from '@/api/client'
import type { RecruitmentPlanRead } from '@/types/subscription'

export async function getPlans(): Promise<RecruitmentPlanRead[]> {
  return apiClient.get<RecruitmentPlanRead, RecruitmentPlanRead[]>('/plans')
}