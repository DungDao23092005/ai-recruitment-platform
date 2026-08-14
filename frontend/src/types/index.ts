export type { HealthStatus } from '@/api/endpoints'

export interface UserRole {
  value: string
  label: string
}

export interface NavLink {
  to: string
  label: string
}

export const USER_ROLES: UserRole[] = [
  { value: 'candidate', label: 'Candidate' },
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'admin', label: 'Admin' },
]