export type SubscriptionStatus = 'pending' | 'active' | 'cancelled' | 'expired'
export type SubscriptionScope =
  | 'company_recruiting'
  | 'candidate_personal'
  | 'legacy_recruiter_personal'
export type PlanAudience = 'company' | 'candidate'
export type SubscriptionUsageFeatureType =
  | 'job_post'
  | 'candidate_search'
  | 'ai_feature'
  | 'recruiting_ai'
  | 'candidate_parse_resume'
  | 'candidate_job_recommendations'
  | 'candidate_chat'
export type SubscriptionUsageStatus = 'reserved' | 'completed' | 'failed'

export interface RecruitmentPlan {
  id: string
  name: string
  description: string
  price: number
  currency: string
  duration_days: number
  max_job_posts: number
  max_candidate_searches: number | null
  max_ai_features: number | null
  plan_audience?: PlanAudience
  is_free?: boolean
  is_active: boolean
  display_order?: number
  features?: string[]
}

export interface Subscription {
  id: string
  user_id: string
  plan_id: string
  status: SubscriptionStatus
  started_at: string | null
  expires_at: string | null
  plan?: RecruitmentPlan
  company_id?: string | null
  scope?: SubscriptionScope | null
  max_job_posts?: number
  max_candidate_searches?: number
  max_ai_features?: number
  job_posts_used?: number
  candidate_searches_used?: number
  ai_features_used?: number
}

export interface SubscriptionRead {
  id: string
  user_id: string
  plan_id: string
  status: SubscriptionStatus
  started_at: string | null
  expires_at: string | null
  plan?: RecruitmentPlan
  company_id?: string | null
  scope?: SubscriptionScope | null
  max_job_posts?: number
  max_candidate_searches?: number
  max_ai_features?: number
  job_posts_used?: number
  candidate_searches_used?: number
  ai_features_used?: number
}

export interface RecruitmentPlanRead {
  id: string
  name: string
  description: string
  price: number
  currency: string
  duration_days: number
  max_job_posts: number
  max_candidate_searches: number | null
  max_ai_features: number | null
  plan_audience?: PlanAudience
  is_free?: boolean
  is_active: boolean
  display_order?: number
  features?: string[]
}

export interface CandidateEntitlementSnapshot {
  id: string
  plan_id: string
  plan_name: string | null
  status: SubscriptionStatus
  is_free: boolean
  started_at: string | null
  expires_at: string | null
  current_period_key: string | null
  max_ai_features: number
  ai_features_used: number
  ai_features_remaining: number
  is_projected: boolean
}

export interface CandidateEntitlementSummary {
  effective_tier: 'free' | 'paid'
  effective_subscription: CandidateEntitlementSnapshot
  free_subscription: CandidateEntitlementSnapshot | null
  paid_subscription: CandidateEntitlementSnapshot | null
  is_paid_exhausted: boolean
  is_projected: boolean
  next_free_reset_at: string | null
}

export interface CandidateUsageItem {
  id: string
  subscription_id: string
  feature_type: SubscriptionUsageFeatureType
  feature_label: string
  amount: number
  status: SubscriptionUsageStatus
  status_label: string
  reference_id: string | null
  created_at: string
  finalized_at: string | null
}

export interface CandidateUsageHistoryResponse {
  items: CandidateUsageItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface CandidateUsageQueryParams {
  page?: number
  page_size?: number
  start_date?: string
  end_date?: string
  feature_type?: SubscriptionUsageFeatureType
  status?: SubscriptionUsageStatus
}

export interface CompanyUsageItem {
  id: string
  subscription_id: string
  user_id: string
  user_email: string | null
  user_full_name: string | null
  feature_type: SubscriptionUsageFeatureType
  feature_label: string
  amount: number
  status: SubscriptionUsageStatus
  status_label: string
  reference_id: string | null
  created_at: string
  finalized_at: string | null
}

export interface CompanyUsageHistoryResponse {
  items: CompanyUsageItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface CompanyUsageQueryParams {
  page?: number
  page_size?: number
  start_date?: string
  end_date?: string
  feature_type?: SubscriptionUsageFeatureType
  user_id?: string
}
