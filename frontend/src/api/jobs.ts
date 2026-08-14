import apiClient from '@/api/client'
import type { Job, JobListParams } from '@/types/job'

export async function getJobs(params: JobListParams): Promise<Job[]> {
  return apiClient.get<Job[], Job[]>('/jobs', { params })
}

export async function getJobById(id: string): Promise<Job> {
  return apiClient.get<Job, Job>(`/jobs/${id}`)
}