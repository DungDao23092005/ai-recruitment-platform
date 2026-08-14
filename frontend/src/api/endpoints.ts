import apiClient from '@/api/client'

export interface HealthStatus {
  status: string
  service?: string
  version?: string
  environment?: string
}

export const endpoints = {
  health: {
    get: () => apiClient.get<HealthStatus, HealthStatus>('/health'),
  },
}

export default endpoints