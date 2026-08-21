import apiClient from '@/api/client'
import type { Interview, InterviewCreate, InterviewUpdate } from '@/types/application'

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

export async function candidateActionInterview(
  applicationId: string,
  interviewId: string,
  action: 'confirm' | 'decline',
  candidateNotes?: string,
): Promise<Interview> {
  const response = await apiClient.patch<Interview>(
    `/applications/${applicationId}/interviews/${interviewId}/action`,
    {
      action,
      candidate_notes: candidateNotes,
    }
  )
  return response.data
}
