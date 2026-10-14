export type SubscriptionStatus = 'pending' | 'active' | 'cancelled' | 'expired'

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
}

export interface SubscriptionRead {
  id: string
  user_id: string
  plan_id: string
  status: SubscriptionStatus
  started_at: string | null
  expires_at: string | null
  plan?: RecruitmentPlan
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
  is_active: boolean
  display_order?: number
  features?: string[]
}