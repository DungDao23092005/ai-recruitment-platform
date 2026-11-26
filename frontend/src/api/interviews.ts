import apiClient from '@/api/client'
import type {
  AssignedInterview,
  CandidateScheduledInterview,
  Interview,
  InterviewAssignment,
  InterviewCreate,
  InterviewEvaluation,
  InterviewEvaluationCreate,
  InterviewEvaluationUpdate,
  InterviewUpdate,
  InterviewerApplication,
  InterviewerInterview,
} from '@/types/application'

export async function listCandidateInterviews(): Promise<CandidateScheduledInterview[]> {
  return apiClient.get<CandidateScheduledInterview[], CandidateScheduledInterview[]>(
    '/applications/mine/interviews',
  )
}

export async function listMyAssignedInterviews(): Promise<AssignedInterview[]> {
  return apiClient.get<AssignedInterview[], AssignedInterview[]>(
    '/interviews/mine',
  )
}

export async function getAssignedInterview(
  interviewId: string,
): Promise<InterviewerInterview> {
  return apiClient.get<InterviewerInterview, InterviewerInterview>(
    `/interviews/${interviewId}`,
  )
}

export async function getInterviewerApplication(
  interviewId: string,
): Promise<InterviewerApplication> {
  return apiClient.get<InterviewerApplication, InterviewerApplication>(
    `/interviews/${interviewId}/application`,
  )
}

export async function scheduleInterview(
  applicationId: string,
  data: InterviewCreate,
): Promise<Interview> {
  return apiClient.post<Interview, Interview>(
    `/applications/${applicationId}/interviews`,
    data,
  )
}

export async function listInterviews(
  applicationId: string,
): Promise<Interview[]> {
  return apiClient.get<Interview[], Interview[]>(
    `/applications/${applicationId}/interviews`,
  )
}

export async function updateInterview(
  interviewId: string,
  data: InterviewUpdate,
): Promise<Interview> {
  return apiClient.patch<Interview, Interview>(
    `/applications/interviews/${interviewId}`,
    data,
  )
}

export async function cancelInterview(
  interviewId: string,
): Promise<Interview> {
  return apiClient.delete<Interview, Interview>(
    `/applications/interviews/${interviewId}`,
  )
}

export async function getInterview(
  interviewId: string,
): Promise<Interview> {
  return apiClient.get<Interview, Interview>(`/applications/interviews/${interviewId}`)
}

export async function candidateActionInterview(
  applicationId: string,
  interviewId: string,
  action: 'confirm' | 'decline',
  candidateNotes?: string,
): Promise<Interview> {
  const response = await apiClient.patch<Interview, Interview>(
    `/applications/${applicationId}/interviews/${interviewId}/action`,
    {
      action,
      candidate_notes: candidateNotes,
    },
  )
  return response
}

export async function listInterviewAssignments(
  interviewId: string,
): Promise<InterviewAssignment[]> {
  return apiClient.get<InterviewAssignment[], InterviewAssignment[]>(
    `/interviews/${interviewId}/assignments`,
  )
}

export async function assignInterview(
  interviewId: string,
  userId: string,
): Promise<InterviewAssignment> {
  return apiClient.post<InterviewAssignment, InterviewAssignment>(
    `/interviews/${interviewId}/assignments`,
    { user_id: userId },
  )
}

export const assignInterviewer = assignInterview

export async function unassignInterview(
  interviewId: string,
  assignmentId: string,
): Promise<void> {
  await apiClient.delete(`/interviews/${interviewId}/assignments/${assignmentId}`)
}

export const unassignInterviewer = unassignInterview

export async function listWorkspaceInterviewEvaluations(
  interviewId: string,
): Promise<InterviewEvaluation[]> {
  return apiClient.get<InterviewEvaluation[], InterviewEvaluation[]>(
    `/interviews/${interviewId}/evaluations`,
  )
}

export async function createWorkspaceInterviewEvaluation(
  interviewId: string,
  data: InterviewEvaluationCreate,
): Promise<InterviewEvaluation> {
  return apiClient.post<InterviewEvaluation, InterviewEvaluation>(
    `/interviews/${interviewId}/evaluations`,
    data,
  )
}

export async function updateWorkspaceInterviewEvaluation(
  interviewId: string,
  evaluationId: string,
  data: InterviewEvaluationUpdate,
): Promise<InterviewEvaluation> {
  return apiClient.patch<InterviewEvaluation, InterviewEvaluation>(
    `/interviews/${interviewId}/evaluations/${evaluationId}`,
    data,
  )
}

export async function submitWorkspaceInterviewEvaluation(
  interviewId: string,
  evaluationId: string,
): Promise<InterviewEvaluation> {
  return apiClient.post<InterviewEvaluation, InterviewEvaluation>(
    `/interviews/${interviewId}/evaluations/${evaluationId}/submit`,
  )
}

export async function deleteWorkspaceInterviewEvaluation(
  interviewId: string,
  evaluationId: string,
): Promise<void> {
  await apiClient.delete(`/interviews/${interviewId}/evaluations/${evaluationId}`)
}
