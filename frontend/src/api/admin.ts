import apiClient from '@/api/client'
import endpoints, { type HealthStatus } from '@/api/endpoints'
import type {
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

export async function deactivateAdminUser(id: string): Promise<AdminUser> {
  return apiClient.patch<AdminUser, AdminUser>(`/admin/users/${id}/deactivate`)
}
