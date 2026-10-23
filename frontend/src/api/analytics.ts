import apiClient from '@/api/client'
import type {
  AnalyticsQueryParams,
  RecruiterAnalytics,
} from '@/types/analytics'

export async function getRecruiterAnalytics(
  params: AnalyticsQueryParams = {},
): Promise<RecruiterAnalytics> {
  return apiClient.get<RecruiterAnalytics, RecruiterAnalytics>(
    '/analytics/recruiter-dashboard',
    { params },
  )
}
