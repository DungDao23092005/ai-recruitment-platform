import apiClient from '@/api/client'
import endpoints, { type HealthStatus } from '@/api/endpoints'
import type {
  AdminCompanyList,
  AdminCompanyListParams,
  AdminJobList,
  AdminJobListParams,
  AdminStats,
  AdminUser,
  AdminUserList,
  AdminUserListParams,
  AdminPlanRead,
  AdminPlanCreate,
  AdminPlanUpdate,
  AdminPlanStatusUpdate,
  AdminSubscriptionList,
  AdminSubscriptionListParams,
  AdminSubscriptionDetail,
  AdminSubscriptionChangePlan,
  AdminSubscriptionRevoke,
  AdminSubscriptionListItem,
} from '@/types/admin'

export async function getAdminStats(): Promise<AdminStats> {
  return apiClient.get<AdminStats, AdminStats>('/admin/stats')
}

export async function getSystemHealth(): Promise<HealthStatus> {
  return endpoints.health.get()
}

export async function getAdminUsers(
  params: AdminUserListParams,
): Promise<AdminUserList> {
  return apiClient.get<AdminUserList, AdminUserList>('/admin/users', { params })
}

export async function getAdminUserById(id: string): Promise<AdminUser> {
  return apiClient.get<AdminUser, AdminUser>(`/admin/users/${id}`)
}

export async function deactivateAdminUser(id: string, payload: { reason: string }): Promise<AdminUser> {
  return apiClient.patch<AdminUser, AdminUser>(`/admin/users/${id}/deactivate`, payload)
}

export async function activateAdminUser(id: string): Promise<AdminUser> {
  return apiClient.patch<AdminUser, AdminUser>(`/admin/users/${id}/activate`)
}

export async function deleteAdminUser(id: string): Promise<AdminUser> {
  return apiClient.delete<AdminUser, AdminUser>(`/admin/users/${id}`)
}

export async function getAdminCompanies(
  params: AdminCompanyListParams,
): Promise<AdminCompanyList> {
  return apiClient.get<AdminCompanyList, AdminCompanyList>('/admin/companies', {
    params,
  })
}

export async function deleteAdminCompany(id: string): Promise<void> {
  await apiClient.delete(`/companies/${id}`)
}

export async function getAdminJobs(
  params: AdminJobListParams,
): Promise<AdminJobList> {
  return apiClient.get<AdminJobList, AdminJobList>('/admin/jobs', {
    params,
  })
}

export async function getAdminPlans(
  params?: { skip?: number; limit?: number; search?: string },
): Promise<AdminPlanRead[]> {
  return apiClient.get<AdminPlanRead[], AdminPlanRead[]>('/admin/plans', { params })
}

export async function getAdminPlan(id: string): Promise<AdminPlanRead> {
  return apiClient.get<AdminPlanRead, AdminPlanRead>(`/admin/plans/${id}`)
}

export async function createAdminPlan(
  data: AdminPlanCreate,
): Promise<AdminPlanRead> {
  return apiClient.post<AdminPlanCreate, AdminPlanRead>('/admin/plans', data)
}

export async function updateAdminPlan(
  id: string,
  data: AdminPlanUpdate,
): Promise<AdminPlanRead> {
  return apiClient.patch<AdminPlanUpdate, AdminPlanRead>(`/admin/plans/${id}`, data)
}

export async function updateAdminPlanStatus(
  id: string,
  data: AdminPlanStatusUpdate,
): Promise<AdminPlanRead> {
  return apiClient.patch<AdminPlanStatusUpdate, AdminPlanRead>(
    `/admin/plans/${id}/status`,
    data,
  )
}

export async function deleteAdminPlan(id: string): Promise<void> {
  await apiClient.delete(`/admin/plans/${id}`)
}

export async function getAdminSubscriptions(
  params: AdminSubscriptionListParams,
): Promise<AdminSubscriptionList> {
  return apiClient.get<AdminSubscriptionList, AdminSubscriptionList>(
    '/admin/subscriptions',
    { params },
  )
}

export async function getAdminSubscription(
  id: string,
): Promise<AdminSubscriptionDetail> {
  return apiClient.get<AdminSubscriptionDetail, AdminSubscriptionDetail>(
    `/admin/subscriptions/${id}`,
  )
}

export async function changeAdminSubscriptionPlan(
  id: string,
  data: AdminSubscriptionChangePlan,
): Promise<AdminSubscriptionListItem> {
  return apiClient.post<AdminSubscriptionChangePlan, AdminSubscriptionListItem>(
    `/admin/subscriptions/${id}/change-plan`,
    data,
  )
}

export async function revokeAdminSubscription(
  id: string,
  data: AdminSubscriptionRevoke,
): Promise<AdminSubscriptionListItem> {
  return apiClient.post<AdminSubscriptionRevoke, AdminSubscriptionListItem>(
    `/admin/subscriptions/${id}/revoke`,
    data,
  )
}
