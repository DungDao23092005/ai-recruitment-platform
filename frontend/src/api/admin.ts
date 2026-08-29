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
