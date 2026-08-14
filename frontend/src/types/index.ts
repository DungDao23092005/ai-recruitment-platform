export type { HealthStatus } from '@/api/endpoints'
export type { UserRole } from '@/types/auth'
export type {
  Job,
  JobListParams,
  JobStatus,
  JobType,
  WorkplaceType,
} from '@/types/job'
export type { Application, ApplicationStatus } from '@/types/application'
export type {
  Company,
  CompanyCreateData,
  CompanySize,
} from '@/types/company'
export type {
  Education,
  ParsedResume,
  WorkExperience,
} from '@/types/ai'

export interface NavLink {
  to: string
  label: string
}

export const USER_ROLES: { value: string; label: string }[] = [
  { value: 'candidate', label: 'Candidate' },
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'admin', label: 'Admin' },
]