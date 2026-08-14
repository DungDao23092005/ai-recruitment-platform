export type { HealthStatus } from '@/api/endpoints'
export type { UserRole } from '@/types/auth'

export interface NavLink {
  to: string
  label: string
}

export const USER_ROLES: { value: string; label: string }[] = [
  { value: 'candidate', label: 'Candidate' },
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'admin', label: 'Admin' },
]