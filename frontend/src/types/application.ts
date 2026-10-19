import type { ParsedJob } from '@/types/ai'

export type ApplicationStatus =
  | 'applied'
  | 'under_review'
  | 'shortlisted'
  | 'interviewing'
  | 'offered'
  | 'accepted'
  | 'rejected'
  | 'withdrawn'

export interface CandidateProfileMinimal {
  id: string
  full_name: string | null
  title: string | null
}

export interface Application {
  id: string
  candidate_id: string
  job_id: string
  status: ApplicationStatus
  created_at: string
  updated_at: string
  candidate: CandidateProfileMinimal | null
}

export interface ApplicationWithJob {
  id: string
  job_id: string
  job_title: string
  company_name: string | null
  status: ApplicationStatus
  created_at: string
  updated_at: string
  interviews?: Interview[]
}

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

export interface Resume {
  id: string
  candidate_id: string
  title: string | null
  is_primary: boolean
  parsed_data: ParsedResume | null
  created_at: string
  updated_at: string
}

export type InterviewType = 'technical' | 'behavioral' | 'hr' | 'case_study'
export type InterviewStatus = 'scheduled' | 'completed' | 'cancelled' | 'candidate_confirmed' | 'candidate_declined'

export interface InterviewCreate {
  scheduled_at: string
  duration_minutes: number
  interview_type: InterviewType
  meeting_url?: string | null
  location?: string | null
  notes?: string | null
}

export interface InterviewUpdate {
  scheduled_at?: string
  duration_minutes?: number
  interview_type?: InterviewType
  meeting_url?: string | null
  location?: string | null
  notes?: string | null
  status?: InterviewStatus
}

export interface Interview {
  id: string
  application_id: string
  scheduled_at: string
  duration_minutes: number
  interview_type: InterviewType
  meeting_url: string | null
  location: string | null
  notes: string | null
  candidate_notes: string | null
  status: InterviewStatus
  created_at: string
  updated_at: string
}

export interface ApplicationDetail {
  id: string
  candidate_id: string
  job_id: string
  job_title: string
  company_name: string | null
  status: ApplicationStatus
  created_at: string
  updated_at: string
  candidate: CandidateProfileMinimal | null
  resume: Resume | null
  parsed_job: ParsedJob | null
  interviews: Interview[]
}

export type EvaluationRecommendation =
  | 'strong_hire'
  | 'hire'
  | 'no_hire'
  | 'strong_no_hire'

export const EVALUATION_RECOMMENDATION_LABELS: Record<
  EvaluationRecommendation,
  string
> = {
  strong_hire: 'Rất nên tuyển',
  hire: 'Nên tuyển',
  no_hire: 'Không nên tuyển',
  strong_no_hire: 'Hoàn toàn không nên tuyển',
}

export interface ApplicationNote {
  id: string
  application_id: string
  author_id: string
  content: string
  created_at: string
  updated_at: string
}

export interface InterviewEvaluation {
  id: string
  interview_id: string
  application_id: string
  evaluator_id: string
  rating: number
  strengths: string | null
  weaknesses: string | null
  recommendation: EvaluationRecommendation | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface InterviewEvaluationCreate {
  rating: number
  strengths?: string | null
  weaknesses?: string | null
  recommendation?: EvaluationRecommendation | null
  notes?: string | null
}

export interface InterviewEvaluationUpdate {
  rating?: number
  strengths?: string | null
  weaknesses?: string | null
  recommendation?: EvaluationRecommendation | null
  notes?: string | null
}

export interface ApplicationActivity {
  id: string
  application_id: string
  actor_id: string
  action_type: string
  from_status: string | null
  to_status: string | null
  note: string | null
  metadata_json: string | null
  created_at: string
}

export interface CandidateActivity {
  id: string
  action_type: string
  from_status: string | null
  to_status: string | null
  created_at: string
}

export type CandidateStage =
  | 'applied'
  | 'under_review'
  | 'interviewing'
  | 'offered'
  | 'outcome'

const CANDIDATE_STAGE_BY_STATUS: Record<ApplicationStatus, CandidateStage> = {
  applied: 'applied',
  under_review: 'under_review',
  shortlisted: 'under_review',
  interviewing: 'interviewing',
  offered: 'offered',
  accepted: 'outcome',
  rejected: 'outcome',
  withdrawn: 'outcome',
}

export function getCandidateStage(status: ApplicationStatus): CandidateStage {
  return CANDIDATE_STAGE_BY_STATUS[status]
}

export interface PageParams {
  skip?: number
  limit?: number
}