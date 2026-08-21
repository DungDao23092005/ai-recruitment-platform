import type { ParsedJob } from '@/types/ai'

export type ApplicationStatus =
  | 'applied'
  | 'under_review'
  | 'shortlisted'
  | 'interviewing'
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
}