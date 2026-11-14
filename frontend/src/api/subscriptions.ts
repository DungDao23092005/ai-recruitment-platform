import apiClient from '@/api/client'
import type {
  CandidateEntitlementSummary,
  CandidateUsageHistoryResponse,
  CandidateUsageQueryParams,
  CompanyUsageHistoryResponse,
  CompanyUsageQueryParams,
  Subscription,
} from '@/types/subscription'
import type { PaymentOrderRead } from '@/types/payment'

export async function getMySubscription(): Promise<Subscription | null> {
  try {
    return await apiClient.get<Subscription, Subscription | null>('/subscriptions/me')
  } catch (error) {
    if ((error as { response?: { status: number } }).response?.status === 404) {
      return null
    }
    throw error
  }
}

export async function getCompanySubscription(): Promise<Subscription | null> {
  try {
    return await apiClient.get<Subscription, Subscription | null>(
      '/subscriptions/company',
    )
  } catch (error) {
    if ((error as { response?: { status: number } }).response?.status === 404) {
      return null
    }
    throw error
  }
}

export async function getCandidateEntitlementSummary(): Promise<CandidateEntitlementSummary> {
  return apiClient.get<CandidateEntitlementSummary, CandidateEntitlementSummary>(
    '/subscriptions/candidate/me',
  )
}

export async function getCandidateUsages(
  params: CandidateUsageQueryParams = {},
): Promise<CandidateUsageHistoryResponse> {
  const query: Record<string, string | number> = {}
  if (params.page !== undefined) query.page = params.page
  if (params.page_size !== undefined) query.page_size = params.page_size
  if (params.start_date) query.start_date = params.start_date
  if (params.end_date) query.end_date = params.end_date
  if (params.feature_type) query.feature_type = params.feature_type
  if (params.status) query.status = params.status

  return apiClient.get<
    CandidateUsageHistoryResponse,
    CandidateUsageHistoryResponse
  >('/subscriptions/candidate/usages', { params: query })
}

export async function getCompanySubscriptionHistory(): Promise<
  PaymentOrderRead[]
> {
  return apiClient.get<PaymentOrderRead[], PaymentOrderRead[]>(
    '/subscriptions/company/history',
  )
}

export async function getCompanyUsages(
  params: CompanyUsageQueryParams = {},
): Promise<CompanyUsageHistoryResponse> {
  const query: Record<string, string | number> = {}
  if (params.page !== undefined) query.page = params.page
  if (params.page_size !== undefined) query.page_size = params.page_size
  if (params.start_date) query.start_date = params.start_date
  if (params.end_date) query.end_date = params.end_date
  if (params.feature_type) query.feature_type = params.feature_type
  if (params.user_id) query.user_id = params.user_id

  return apiClient.get<CompanyUsageHistoryResponse, CompanyUsageHistoryResponse>(
    '/subscriptions/company/usages',
    { params: query },
  )
}
