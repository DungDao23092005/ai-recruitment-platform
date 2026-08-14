export type ApplicationStatus =
  | 'applied'
  | 'under_review'
  | 'shortlisted'
  | 'interviewing'
  | 'accepted'
  | 'rejected'
  | 'withdrawn'

export interface Application {
  id: string
  candidate_id: string
  job_id: string
  status: ApplicationStatus
  created_at: string
  updated_at: string
}