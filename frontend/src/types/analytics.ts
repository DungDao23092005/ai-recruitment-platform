export interface AnalyticsQuotaLine {
  limit: number | null
  used: number
  remaining: number | null
}

export interface AnalyticsQuotaStatus {
  subscription_status: 'active' | 'none'
  plan_name: string | null
  expires_at: string | null
  job_posts: AnalyticsQuotaLine
  candidate_searches: AnalyticsQuotaLine
  ai_features: AnalyticsQuotaLine
}

export interface AnalyticsKpis {
  total_views: number
  unique_views: number
  unverified_views: number
  total_applications: number
  hires: number
  conversion_rate: number
  avg_time_to_hire_days: number | null
}

export type AnalyticsFunnelStageKey =
  | 'applied'
  | 'under_review'
  | 'interviewing'
  | 'offered'
  | 'accepted'

export interface AnalyticsFunnelStage {
  stage: AnalyticsFunnelStageKey
  count: number
}

export interface AnalyticsDailyPoint {
  date: string
  total_views: number
  unique_views: number
  unverified_views: number
}

export interface AnalyticsJobRow {
  job_id: string
  job_title: string
  job_status: string
  total_views: number
  unique_views: number
  unverified_views: number
  applications: number
  hires: number
}

export interface AnalyticsDataQuality {
  unique_views_reliable: boolean
  raw_fallback_dates: string[]
  note: string
}

export interface RecruiterAnalytics {
  timezone: string
  start_date: string
  end_date: string
  generated_at: string
  kpis: AnalyticsKpis
  funnel: AnalyticsFunnelStage[]
  daily_views: AnalyticsDailyPoint[]
  jobs: AnalyticsJobRow[]
  quota: AnalyticsQuotaStatus
  data_quality: AnalyticsDataQuality
}

export interface AnalyticsQueryParams {
  start_date?: string
  end_date?: string
  job_id?: string
}
