export interface ApplicationStatusCounts {
  applied: number
  under_review: number
  shortlisted: number
  interviewing: number
  accepted: number
  rejected: number
  withdrawn: number
}

export interface AdminStats {
  total_users: number
  total_candidates: number
  total_recruiters: number
  total_admins: number
  total_companies: number
  total_jobs: number
  total_applications: number
  applications_by_status: ApplicationStatusCounts
}

export interface AdminUser {
  id: string
  email: string
  role: 'admin' | 'candidate' | 'recruiter'
  is_active: boolean
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface AdminUserList {
  items: AdminUser[]
  total: number
  skip: number
  limit: number
}

export interface AdminUserListParams {
  skip: number
  limit: number
  search?: string
  role?: 'admin' | 'candidate' | 'recruiter'
}
