export type UserRole = 'admin' | 'candidate' | 'recruiter'

export interface User {
  id: string
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Token {
  access_token: string
  token_type: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterData {
  email: string
  password: string
  role: Exclude<UserRole, 'admin'>
}

export interface CandidateProfile {
  id: string
  user_id: string
  full_name: string | null
  phone: string | null
  title: string | null
}

export interface CandidateProfileRead {
  id: string
  user_id: string
  full_name: string | null
  phone: string | null
  title: string | null
}

export interface CandidateProfileData {
  full_name: string | null
  phone: string | null
  title: string | null
}

export interface CandidateProfileUpdate {
  full_name: string | null
  phone: string | null
  title: string | null
}

export interface RecruiterProfile {
  id: string
  user_id: string
  company_id: string | null
  full_name: string | null
  position: string | null
}

export interface RecruiterProfileData {
  full_name: string | null
  position: string | null
  company_id: string | null
}

export const USER_ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Quản trị viên',
  candidate: 'Ứng viên',
  recruiter: 'Nhà tuyển dụng',
}