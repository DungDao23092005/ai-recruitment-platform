import apiClient from '@/api/client'
import type { Application } from '@/types/application'

export async function applyJob(jobId: string): Promise<Application> {
  return apiClient.post<Application, Application>('/applications', {
    job_id: jobId,
  })
}

export async function getApplicationsByJob(
  jobId: string,
): Promise<Application[]> {
  return apiClient.get<Application[], Application[]>('/applications', {
    params: { job_id: jobId },
  })
}