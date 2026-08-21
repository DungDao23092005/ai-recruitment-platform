export interface JobStatusCount {
  status: string
  count: number
}

export interface ApplicationStatusCount {
  status: string
  count: number
}

export interface RecruiterMetrics {
  total_jobs: number
  total_applications: number
  jobs_by_status: JobStatusCount[]
  applications_by_status: ApplicationStatusCount[]
}