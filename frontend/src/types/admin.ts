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

export type AdminCompanySize = 'seed' | 'startup' | 'sme' | 'enterprise'

export interface AdminCompany {
  id: string
  name: string
  slug: string
  tax_code: string
  size: AdminCompanySize
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface AdminCompanyList {
  items: AdminCompany[]
  total: number
  skip: number
  limit: number
}

export interface AdminCompanyListParams {
  skip: number
  limit: number
  search?: string
}

export interface AdminJob {
  id: string
  company_id: string
  company_name: string | null
  title: string
  description: string
  status: 'draft' | 'published' | 'closed' | 'expired'
  job_type: 'full_time' | 'part_time' | 'contract' | 'internship'
  workplace_type: 'on_site' | 'hybrid' | 'remote'
  location: string
  created_at: string
  updated_at: string
}

export interface AdminJobList {
  items: AdminJob[]
  total: number
  skip: number
  limit: number
}

export interface AdminJobListParams {
  skip: number
  limit: number
  search?: string
}

export interface AdminPlanRead {
  id: string
  name: string
  description: string | null
  price: number
  currency: string
  duration_days: number
  max_job_posts: number
  max_candidate_searches: number
  max_ai_features: number
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AdminPlanCreate {
  name: string
  description: string | null
  price: number
  currency: string
  duration_days: number
  max_job_posts: number
  max_candidate_searches: number
  max_ai_features: number
  display_order: number
}

export interface AdminPlanUpdate {
  name?: string
  description?: string | null
  price?: number
  currency?: string
  duration_days?: number
  max_job_posts?: number
  max_candidate_searches?: number
  max_ai_features?: number
  display_order?: number
  is_active?: boolean
}

export interface AdminPlanStatusUpdate {
  is_active: boolean
}

export type AdminSubscriptionStatus = 'active' | 'expired' | 'cancelled' | 'pending'

export type AdminSubscriptionAuditAction = 'provision' | 'change_plan' | 'revoke'

export interface AdminSubscriptionListItem {
  id: string
  user_id: string
  user_email: string | null
  plan_id: string
  plan_name: string | null
  status: AdminSubscriptionStatus
  effective_status: AdminSubscriptionStatus
  started_at: string | null
  expires_at: string | null
  created_at: string
  updated_at: string
  max_job_posts: number
  max_candidate_searches: number
  max_ai_features: number
  job_posts_used: number
  candidate_searches_used: number
  ai_features_used: number
  total_subscriptions: number
  has_multiple_active: boolean
  has_unresolved_payment: boolean
  is_entitlement_incident: boolean
  incident_subscription_id: string | null
  incident_internal_order_id: string | null
  incident_amount: number | null
}

export interface AdminSubscriptionList {
  items: AdminSubscriptionListItem[]
  total: number
  skip: number
  limit: number
}

export interface AdminSubscriptionListParams {
  skip: number
  limit: number
  search?: string
  status_filter?: AdminSubscriptionStatus
}

export interface AdminSubscriptionAuditLog {
  id: string
  admin_id: string
  admin_email: string | null
  user_id: string
  subscription_id: string
  action: AdminSubscriptionAuditAction
  old_plan_id: string | null
  new_plan_id: string | null
  reason: string
  created_at: string
}

export interface AdminSubscriptionPaymentSummary {
  id: string
  plan_id: string
  subscription_id: string | null
  internal_order_id: string
  provider: string
  status: string
  amount: number
  currency: string
  paid_at: string | null
  expired_at: string | null
  created_at: string
}

export interface AdminSubscriptionSummary {
  id: string
  plan_id: string
  plan_name: string | null
  status: AdminSubscriptionStatus
  started_at: string | null
  expires_at: string | null
  created_at: string
  max_job_posts: number
  max_candidate_searches: number
  max_ai_features: number
  job_posts_used: number
  candidate_searches_used: number
  ai_features_used: number
  payments: AdminSubscriptionPaymentSummary[]
}

export interface AdminSubscriptionDetail {
  subscription: AdminSubscriptionListItem
  history: AdminSubscriptionSummary[]
  audit_logs: AdminSubscriptionAuditLog[]
}

export interface AdminSubscriptionChangePlan {
  target_plan_id: string
  reason: string
}

export interface AdminSubscriptionRevoke {
  reason: string
}

export type AdminEmailStatus = 'pending' | 'processing' | 'sent' | 'failed'

export interface AdminEmailOutboxMessage {
  id: string
  event_type: string
  to_email: string
  subject: string
  status: AdminEmailStatus
  attempts: number
  max_attempts: number
  next_attempt_at: string
  processing_started_at: string | null
  sent_at: string | null
  last_error: string | null
  created_at: string
  updated_at: string
}

export interface AdminEmailOutboxList {
  items: AdminEmailOutboxMessage[]
  total: number
  skip: number
  limit: number
}

export interface AdminEmailOutboxListParams {
  skip: number
  limit: number
  status?: AdminEmailStatus
  event_type?: string
  search?: string
}

export interface AdminEmailOutboxStats {
  pending: number
  processing: number
  sent: number
  failed: number
  total: number
  oldest_pending_created_at: string | null
}

export type AdminAuditAction = 'user_lock' | 'user_unlock' | 'user_delete'

export interface AdminAuditLog {
  id: string
  admin_id: string
  admin_email: string | null
  target_user_id: string
  target_user_email: string | null
  action: AdminAuditAction
  reason: string | null
  details: Record<string, unknown> | null
  created_at: string
}

export interface AdminAuditLogList {
  items: AdminAuditLog[]
  total: number
  skip: number
  limit: number
}

export interface AdminAuditLogListParams {
  skip: number
  limit: number
  action?: AdminAuditAction
  admin_id?: string
  target_user_id?: string
  created_from?: string
  created_to?: string
  search?: string
}
