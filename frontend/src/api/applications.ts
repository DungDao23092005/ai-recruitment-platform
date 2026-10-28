import apiClient from '@/api/client'
import type {
  ApplicationMatchExplanationResponse,
  MatchResult,
} from '@/types/ai'
import type {
  Application,
  ApplicationActivity,
  ApplicationDetail,
  ApplicationNote,
  ApplicationStatus,
  ApplicationWithJob,
  CandidateActivity,
  InterviewEvaluation,
  InterviewEvaluationCreate,
  InterviewEvaluationUpdate,
  OfferAction,
  PageParams,
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

export async function respondToOffer(
  applicationId: string,
  action: OfferAction,
  notes?: string,
): Promise<Application> {
  return apiClient.patch<Application, Application>(
    `/applications/mine/${applicationId}/offer`,
    { action, ...(notes ? { notes } : {}) },
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

export async function getApplicationMatch(
  applicationId: string,
): Promise<MatchResult> {
  return apiClient.get<MatchResult, MatchResult>(
    `/applications/${applicationId}/match`,
  )
}

export async function getApplicationMatchExplanation(
  applicationId: string,
): Promise<ApplicationMatchExplanationResponse> {
  return apiClient.get<
    ApplicationMatchExplanationResponse,
    ApplicationMatchExplanationResponse
  >(`/applications/${applicationId}/match-explanation`)
}

export async function refreshApplicationMatchExplanation(
  applicationId: string,
  idempotencyKey?: string,
): Promise<ApplicationMatchExplanationResponse> {
  const key = idempotencyKey || crypto.randomUUID()
  return apiClient.post<
    ApplicationMatchExplanationResponse,
    ApplicationMatchExplanationResponse
  >(
    `/applications/${applicationId}/match-explanation/refresh`,
    {},
    {
      headers: {
        'Idempotency-Key': key,
      },
    },
  )
}

export interface MyApplicationsParams {
  skip?: number
  limit?: number
  job_id?: string
}

export async function getMyApplications(
  params: MyApplicationsParams = {},
): Promise<ApplicationWithJob[]> {
  return apiClient.get<ApplicationWithJob[], ApplicationWithJob[]>(
    '/applications/mine',
    { params },
  )
}

export async function getMyApplication(
  applicationId: string,
): Promise<ApplicationWithJob> {
  return apiClient.get<ApplicationWithJob, ApplicationWithJob>(
    `/applications/mine/${applicationId}`,
  )
}

export async function getMyApplicationTimeline(
  applicationId: string,
  params: PageParams = {},
): Promise<CandidateActivity[]> {
  return apiClient.get<CandidateActivity[], CandidateActivity[]>(
    `/applications/mine/${applicationId}/timeline`,
    { params },
  )
}

export async function getMyApplicationForJob(
  jobId: string,
): Promise<ApplicationWithJob | null> {
  const result = await apiClient.get<ApplicationWithJob[], ApplicationWithJob[]>(
    '/applications/mine',
    { params: { job_id: jobId } },
  )
  return result[0] ?? null
}

export async function updateApplicationStatus(
  applicationId: string,
  status: ApplicationStatus,
): Promise<Application> {
  return apiClient.patch<Application, Application>(
    `/applications/${applicationId}/status`,
    { status },
  )
}

export async function listApplicationNotes(
  applicationId: string,
  params: PageParams = {},
): Promise<ApplicationNote[]> {
  return apiClient.get<ApplicationNote[], ApplicationNote[]>(
    `/applications/${applicationId}/notes`,
    { params },
  )
}

export async function createApplicationNote(
  applicationId: string,
  content: string,
): Promise<ApplicationNote> {
  return apiClient.post<ApplicationNote, ApplicationNote>(
    `/applications/${applicationId}/notes`,
    { content },
  )
}

export async function updateApplicationNote(
  applicationId: string,
  noteId: string,
  content: string,
): Promise<ApplicationNote> {
  return apiClient.patch<ApplicationNote, ApplicationNote>(
    `/applications/${applicationId}/notes/${noteId}`,
    { content },
  )
}

export async function deleteApplicationNote(
  applicationId: string,
  noteId: string,
): Promise<void> {
  await apiClient.delete<void, void>(
    `/applications/${applicationId}/notes/${noteId}`,
  )
}

export async function listApplicationEvaluations(
  applicationId: string,
): Promise<InterviewEvaluation[]> {
  return apiClient.get<InterviewEvaluation[], InterviewEvaluation[]>(
    `/applications/${applicationId}/evaluations`,
  )
}

export async function listInterviewEvaluations(
  applicationId: string,
  interviewId: string,
): Promise<InterviewEvaluation[]> {
  return apiClient.get<InterviewEvaluation[], InterviewEvaluation[]>(
    `/applications/${applicationId}/interviews/${interviewId}/evaluations`,
  )
}

export async function createInterviewEvaluation(
  applicationId: string,
  interviewId: string,
  data: InterviewEvaluationCreate,
): Promise<InterviewEvaluation> {
  return apiClient.post<InterviewEvaluation, InterviewEvaluation>(
    `/applications/${applicationId}/interviews/${interviewId}/evaluations`,
    data,
  )
}

export async function updateInterviewEvaluation(
  applicationId: string,
  evaluationId: string,
  data: InterviewEvaluationUpdate,
): Promise<InterviewEvaluation> {
  return apiClient.patch<InterviewEvaluation, InterviewEvaluation>(
    `/applications/${applicationId}/evaluations/${evaluationId}`,
    data,
  )
}

export async function deleteInterviewEvaluation(
  applicationId: string,
  evaluationId: string,
): Promise<void> {
  await apiClient.delete<void, void>(
    `/applications/${applicationId}/evaluations/${evaluationId}`,
  )
}

export async function listApplicationActivities(
  applicationId: string,
  params: PageParams = {},
): Promise<ApplicationActivity[]> {
  return apiClient.get<ApplicationActivity[], ApplicationActivity[]>(
    `/applications/${applicationId}/activities`,
    { params },
  )
}
