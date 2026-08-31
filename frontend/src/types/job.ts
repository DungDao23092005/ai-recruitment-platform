export type JobStatus = 'draft' | 'published' | 'closed' | 'expired'

export type JobType = 'full_time' | 'part_time' | 'contract' | 'internship'

export type WorkplaceType = 'on_site' | 'hybrid' | 'remote'

export interface Job {
  id: string
  company_id: string
  company_name: string | null
  title: string
  description: string
  status: JobStatus
  job_type: JobType
  workplace_type: WorkplaceType
  location: string
  skills: string[]
  created_at: string
  updated_at: string
}

export interface JobListParams {
  skip: number
  limit: number
  keyword?: string
  workplace_type?: WorkplaceType
  job_type?: JobType
  location?: string
}

export const JOB_TYPE_LABELS: Record<JobType, string> = {
  full_time: 'Toàn thời gian',
  part_time: 'Bán thời gian',
  contract: 'Hợp đồng',
  internship: 'Thực tập sinh',
}

export const WORKPLACE_TYPE_LABELS: Record<WorkplaceType, string> = {
  on_site: 'Tại văn phòng',
  hybrid: 'Hybrid',
  remote: 'Từ xa',
}

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  draft: 'Bản nháp',
  published: 'Đã đăng',
  closed: 'Đã đóng',
  expired: 'Hết hạn',
}