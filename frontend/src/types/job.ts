export type JobStatus = 'draft' | 'published' | 'closed' | 'expired'

export type JobType = 'full_time' | 'part_time' | 'contract' | 'internship'

export type WorkplaceType = 'on_site' | 'hybrid' | 'remote'

export interface Job {
  id: string
  company_id: string
  title: string
  description: string
  status: JobStatus
  job_type: JobType
  workplace_type: WorkplaceType
  location: string
  created_at: string
  updated_at: string
}

export interface JobListParams {
  skip: number
  limit: number
}

export const JOB_TYPE_LABELS: Record<JobType, string> = {
  full_time: 'Full time',
  part_time: 'Part time',
  contract: 'Contract',
  internship: 'Internship',
}

export const WORKPLACE_TYPE_LABELS: Record<WorkplaceType, string> = {
  on_site: 'On-site',
  hybrid: 'Hybrid',
  remote: 'Remote',
}

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  draft: 'Draft',
  published: 'Published',
  closed: 'Closed',
  expired: 'Expired',
}