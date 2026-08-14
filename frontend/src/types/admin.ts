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
