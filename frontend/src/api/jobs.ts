import apiClient from '@/api/client'
import type {
  Job,
  JobListParams,
  JobStatus,
  JobType,
  WorkplaceType,
} from '@/types/job'

export interface JobUpdatePayload {
  title?: string
  description?: string
  job_type?: JobType
  workplace_type?: WorkplaceType
  location?: string | null
}

export async function getJobs(params: JobListParams): Promise<Job[]> {
  return apiClient.get<Job[], Job[]>('/jobs', { params })
}

export async function getMyJobs(params: JobListParams): Promise<Job[]> {
  return apiClient.get<Job[], Job[]>('/jobs/mine', { params })
}

export async function getJobById(id: string): Promise<Job> {
  return apiClient.get<Job, Job>(`/jobs/${id}`)
}

export async function getMyJobById(id: string): Promise<Job> {
  return apiClient.get<Job, Job>(`/jobs/mine/${id}`)
}

export async function updateMyJob(
  id: string,
  data: JobUpdatePayload,
): Promise<Job> {
  return apiClient.patch<Job, Job>(`/jobs/mine/${id}`, data)
}

export async function updateMyJobStatus(
  id: string,
  status: JobStatus,
): Promise<Job> {
  return apiClient.patch<Job, Job>(`/jobs/mine/${id}/status`, { status })
}

export async function deleteMyJob(id: string): Promise<void> {
  return apiClient.delete<void, void>(`/jobs/mine/${id}`)
}