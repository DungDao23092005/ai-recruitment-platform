export interface WorkExperience {
  company: string | null
  position: string | null
  start_date: string | null
  end_date: string | null
  is_current: boolean
  description: string | null
  skills_used: string[]
}

export interface Education {
  institution: string | null
  degree: string | null
  field_of_study: string | null
  start_year: number | null
  end_year: number | null
}

export interface ParsedResume {
  full_name: string | null
  email: string | null
  phone: string | null
  title: string | null
  summary: string | null
  total_years_experience: number | null
  skills: string[]
  experiences: WorkExperience[]
  education: Education[]
  certifications: string[]
  languages: string[]
}

export interface ResumeRead {
  id: string
  candidate_id: string
  title: string | null
  is_primary: boolean
  parsed_data: ParsedResume | null
  created_at: string
  updated_at: string
}

export interface ParsedJob {
  title: string | null
  summary: string | null
  required_skills: string[]
  preferred_skills: string[]
  minimum_years_experience: number | null
  education_level: string | null
}

export interface MatchResult {
  overall_score: number
  cosine_similarity: number
  skill_coverage_score: number
  preferred_skill_coverage_score: number
  experience_match_score: number
  education_score: number
  project_score: number
  matching_skills: string[]
  skill_gap: string[]
  match_reasons: string[]
  has_required_skills: boolean
  has_preferred_skills: boolean
  has_experience_requirement: boolean
  has_education_requirement: boolean
}

export interface JobMatchRecommendation {
  job_id: string
  parsed_job: ParsedJob | null
  match_result: MatchResult
}

export interface CandidateMatchRecommendation {
  candidate_id: string
  parsed_resume: ParsedResume | null
  match_result: MatchResult
}

export interface MatchRequest {
  parsed_resume: ParsedResume
  parsed_job: ParsedJob
}

export interface ExplainMatchRequest {
  match_result: MatchResult
  candidate?: ParsedResume | null
  job?: ParsedJob | null
}

export interface EvidenceItem {
  source: string
  section: string
  content: string
}

export interface ExplainMatchResponse {
  match_score: number
  summary: string
  strengths: string[]
  missing_skills: string[]
  experience_analysis: string
  education_analysis: string
  evidence: EvidenceItem[]
  recommendation: string
  confidence: number
}

export interface SemanticSearchResult {
  id: string
  score: number
  skills: string[]
  created_at: string | null
  full_name: string | null
  title: string | null
  company_name: string | null
  location: string | null
}

export interface SemanticSearchParams {
  q: string
  limit?: number
  score_threshold?: number
}

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  role: ChatRole
  content: string
}

export type ChatSourceType = 'job' | 'resume'

export interface ChatSource {
  source_type: ChatSourceType
  entity_id: string
  title: string
  relevance_score: number
  skills: string[]
}

export interface ChatRequest {
  message: string
  history?: ChatMessage[]
}

export interface ChatResponse {
  answer: string
  confidence?: number
  sources: ChatSource[]
  suggested_followups: string[]
}

export type QuestionCategory =
  | 'technical'
  | 'behavioral'
  | 'experience'
  | 'project'
  | 'skill_gap'

export type QuestionDifficulty = 'easy' | 'medium' | 'hard'

export type QuestionGenerationDifficulty =
  | 'easy'
  | 'medium'
  | 'hard'
  | 'mixed'

export interface InterviewQuestion {
  question: string
  reason: string
  category: QuestionCategory
  difficulty: QuestionDifficulty
  target_skill_or_topic: string
  evaluation_criteria: string
  sample_answer_points: string[]
}

export interface GenerateInterviewQuestionsRequest {
  job: ParsedJob
  candidate?: ParsedResume | null
  match_result?: MatchResult | null
  num_questions: number
  difficulty: QuestionGenerationDifficulty
  focus_areas: string[]
}

export interface GenerateInterviewQuestionsResponse {
  job_title: string
  candidate_title: string | null
  total_questions: number
  questions: InterviewQuestion[]
}