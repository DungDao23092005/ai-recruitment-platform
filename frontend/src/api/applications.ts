import apiClient from '@/api/client'
import type {
  Application,
  ApplicationDetail,
  ApplicationWithJob,
} from '@/types/application'

export async function applyJob(jobId: string): Promise<Application> {
  return apiClient.post<Application, Application>('/applications', {
    job_id: jobId,
  })
}

export async function withdrawApplication(
  applicationId: string,
): Promise<Application> {
  return apiClient.patch<Application, Application>(
    `/applications/mine/${applicationId}/withdraw`,
  )
}

export async function getApplicationsByJob(
  jobId: string,
): Promise<Application[]> {
  return apiClient.get<Application[], Application[]>('/applications', {
    params: { job_id: jobId },
  })
}

export async function getApplicationDetail(
  applicationId: string,
): Promise<ApplicationDetail> {
  return apiClient.get<ApplicationDetail, ApplicationDetail>(
    `/applications/${applicationId}`,
  )
}

export interface MyApplicationsParams {
  skip?: number
  limit?: number
}

export async function getMyApplications(
  params: MyApplicationsParams = {},
): Promise<ApplicationWithJob[]> {
  return apiClient.get<ApplicationWithJob[], ApplicationWithJob[]>(
    '/applications/mine',
    { params },
  )
}