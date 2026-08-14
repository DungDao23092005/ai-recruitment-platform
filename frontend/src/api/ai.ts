import apiClient from '@/api/client'
import type {
  CandidateMatchRecommendation,
  JobMatchRecommendation,
  MatchRequest,
  MatchResult,
  ParsedResume,
} from '@/types/ai'

export async function parseResume(file: File): Promise<ParsedResume> {
  const formData = new FormData()
  formData.append('file', file)

  return apiClient.post<ParsedResume, ParsedResume>(
    '/ai/parse-resume',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  )
}

export async function getJobRecommendations(
  limit = 10,
): Promise<JobMatchRecommendation[]> {
  return apiClient.get<JobMatchRecommendation[], JobMatchRecommendation[]>(
    '/ai/recommendations/jobs',
    {
      params: { limit },
    },
  )
}

export async function getCandidateRecommendations(
  jobId: string,
  limit = 10,
): Promise<CandidateMatchRecommendation[]> {
  return apiClient.get<
    CandidateMatchRecommendation[],
    CandidateMatchRecommendation[]
  >('/ai/recommendations/candidates', {
    params: { job_id: jobId, limit },
  })
}

export async function matchCandidateWithJob(
  data: MatchRequest,
): Promise<MatchResult> {
  return apiClient.post<MatchResult, MatchResult>('/ai/match', data)
}