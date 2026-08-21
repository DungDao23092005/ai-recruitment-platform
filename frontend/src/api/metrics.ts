import apiClient from '@/api/client'
import type { RecruiterMetrics } from '@/types/metrics'

export async function getRecruiterMetrics(): Promise<RecruiterMetrics> {
  return apiClient.get<RecruiterMetrics, RecruiterMetrics>('/users/me/recruiter-metrics')
}