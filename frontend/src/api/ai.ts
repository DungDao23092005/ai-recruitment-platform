import apiClient from '@/api/client'
import type {
  CandidateMatchRecommendation,
  ChatRequest,
  ChatResponse,
  ExplainMatchRequest,
  ExplainMatchResponse,
  JobMatchRecommendation,
  MatchRequest,
  MatchResult,
  ParsedResume,
  SemanticSearchParams,
  SemanticSearchResult,
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

export async function explainMatch(
  data: ExplainMatchRequest,
): Promise<ExplainMatchResponse> {
  return apiClient.post<ExplainMatchResponse, ExplainMatchResponse>(
    '/ai/explain-match',
    data,
  )
}

export async function searchJobs(
  params: SemanticSearchParams,
): Promise<SemanticSearchResult[]> {
  return apiClient.get<SemanticSearchResult[], SemanticSearchResult[]>(
    '/ai/search/jobs',
    {
      params: {
        q: params.q,
        limit: params.limit ?? 10,
        score_threshold: params.score_threshold,
      },
    },
  )
}

export async function searchCandidates(
  params: SemanticSearchParams,
): Promise<SemanticSearchResult[]> {
  return apiClient.get<SemanticSearchResult[], SemanticSearchResult[]>(
    '/ai/search/candidates',
    {
      params: {
        q: params.q,
        limit: params.limit ?? 10,
        score_threshold: params.score_threshold,
      },
    },
  )
}

export async function sendChatMessage(
  data: ChatRequest,
): Promise<ChatResponse> {
  return apiClient.post<ChatResponse, ChatResponse>('/ai/chat', data)
}