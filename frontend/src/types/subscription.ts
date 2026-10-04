export type SubscriptionStatus = 'pending' | 'active' | 'cancelled' | 'expired'

export interface RecruitmentPlan {
  id: string
  name: string
  description: string
  price: number
  currency: string
  duration_days: number
  max_job_posts: number
  is_active: boolean
  display_order?: number
  features?: string[]
}

export interface Subscription {
  id: string
  user_id: string
  plan_id: string
  status: SubscriptionStatus
  start_date?: string
  end_date?: string
  plan?: RecruitmentPlan
}

export interface SubscriptionRead {
  id: string
  user_id: string
  plan_id: string
  status: SubscriptionStatus
  start_date?: string
  end_date?: string
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
  is_active: boolean
  display_order?: number
  features?: string[]
}