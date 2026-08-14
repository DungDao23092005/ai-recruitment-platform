import apiClient from '@/api/client'
import endpoints, { type HealthStatus } from '@/api/endpoints'
import type { AdminStats } from '@/types/admin'

export async function getAdminStats(): Promise<AdminStats> {
  return apiClient.get<AdminStats, AdminStats>('/admin/stats')
}

export async function getSystemHealth(): Promise<HealthStatus> {
  return endpoints.health.get()
}
