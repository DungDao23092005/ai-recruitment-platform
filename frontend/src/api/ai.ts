import apiClient from '@/api/client'
import { AxiosError } from 'axios'
import type {
  CandidateMatchRecommendation,
  ChatRequest,
  ChatResponse,
  ExplainMatchRequest,
  ExplainMatchResponse,
  GenerateInterviewQuestionsRequest,
  GenerateInterviewQuestionsResponse,
  JobMatchRecommendation,
  MatchRequest,
  MatchResult,
  ParsedResume,
  ResumeRead,
  SemanticSearchParams,
  SemanticSearchResult,
} from '@/types/ai'

export interface JobRecommendationsResult {
  recommendations: JobMatchRecommendation[]
  hasCV: boolean
}

export async function parseResume(file: File): Promise<ParsedResume> {
  const formData = new FormData()
  formData.append('file', file)

  return apiClient.post<ParsedResume, ParsedResume>(
    '/ai/parse-resume',
    formData
  )
}

export async function getMyResume(): Promise<ResumeRead> {
  return apiClient.get<ResumeRead, ResumeRead>('/users/me/resume')
}

export async function getJobRecommendations(
  limit = 10,
): Promise<JobRecommendationsResult> {
  try {
    const recommendations = await apiClient.get<JobMatchRecommendation[], JobMatchRecommendation[]>(
      '/ai/recommendations/jobs',
      {
        params: { limit },
      },
    )
    return { recommendations, hasCV: true }
  } catch (error) {
    if (error instanceof AxiosError && error.response?.status === 404) {
      return { recommendations: [], hasCV: false }
    }
    throw error
  }
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

export async function generateInterviewQuestions(
  data: GenerateInterviewQuestionsRequest,
): Promise<GenerateInterviewQuestionsResponse> {
  return apiClient.post<
    GenerateInterviewQuestionsResponse,
    GenerateInterviewQuestionsResponse
  >('/ai/generate-interview-questions', data)
}