import { useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { usePlans } from '@/features/subscriptions/hooks/usePlans'
import { useCandidateEntitlement } from '@/features/subscriptions/hooks/useCandidateEntitlement'
import { useCompanySubscription } from '@/features/subscriptions/hooks/useCompanySubscription'
import { PlanCard } from '@/features/subscriptions/components/PlanCard'
import { CurrentSubscriptionCard } from '@/features/subscriptions/components/CurrentSubscriptionCard'
import { useAuth } from '@/contexts/AuthContext'
import { useOptionalWorkspace } from '@/contexts/WorkspaceContext'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import type { RecruitmentPlan, RecruitmentPlanRead } from '@/types/subscription'

export function PlansPage() {
  const { currentUser } = useAuth()
  const workspace = useOptionalWorkspace()
  const navigate = useNavigate()

  const isCandidate = currentUser?.role === 'candidate'
  const isRecruiter = currentUser?.role === 'recruiter'

  const { plans, isLoading, error, refetch } = usePlans(
    isRecruiter ? 'company' : isCandidate ? 'candidate' : undefined,
  )
  const candidateEntitlement = useCandidateEntitlement(isCandidate)
  const companySubscription = useCompanySubscription(isRecruiter)

  const activeSubscription = isRecruiter
    ? companySubscription.subscription
    : null
  const isSubscriptionLoading = isRecruiter
    ? companySubscription.isLoading
    : false
  const subscriptionError = isRecruiter ? companySubscription.error : null

  // A missing provider (e.g. isolated rendering) keeps the historical
  // permissive behaviour; the backend remains the authority for checkout.
  const isWorkspaceAdmin = workspace
    ? workspace.selectedWorkspace?.role === 'admin'
    : true
  const canPurchase = !isRecruiter || isWorkspaceAdmin

  const candidateSnapshot = candidateEntitlement.entitlement
    ?.effective_subscription
  const candidateIsPaid =
    candidateEntitlement.entitlement?.effective_tier === 'paid'

  const isCurrentPlan = useCallback(
    (planId: string): boolean => {
      if (isCandidate) {
        if (
          candidateEntitlement.isLoading ||
          candidateEntitlement.error ||
          !candidateSnapshot
        ) {
          return false
        }
        return (
          candidateSnapshot.status === 'active' &&
          candidateSnapshot.plan_id === planId
        )
      }
      if (isSubscriptionLoading || subscriptionError || !activeSubscription) {
        return false
      }
      if (activeSubscription.status !== 'active') {
        return false
      }
      if (activeSubscription.plan_id !== planId) {
        return false
      }
      if (activeSubscription.expires_at) {
        const expiresAt = new Date(activeSubscription.expires_at).getTime()
        if (Number.isNaN(expiresAt) || expiresAt <= Date.now()) {
          return false
        }
      }
      return true
    },
    [
      activeSubscription,
      candidateEntitlement.error,
      candidateEntitlement.isLoading,
      candidateSnapshot,
      isCandidate,
      isSubscriptionLoading,
      subscriptionError,
    ],
  )

  const currentPlan = useMemo<RecruitmentPlan | RecruitmentPlanRead | null>(() => {
    if (isCandidate) {
      if (
        candidateEntitlement.isLoading ||
        candidateEntitlement.error ||
        !candidateIsPaid ||
        !candidateSnapshot
      ) {
        return null
      }

      if (candidateSnapshot.status !== 'active') {
        return null
      }

      if (candidateSnapshot.expires_at) {
        const expiresAt = new Date(candidateSnapshot.expires_at).getTime()
        if (Number.isNaN(expiresAt) || expiresAt <= Date.now()) {
          return null
        }
      }

      return (
        plans.find((plan) => plan.id === candidateSnapshot.plan_id) ||
        ({
          id: candidateSnapshot.plan_id,
          name: candidateSnapshot.plan_name ?? 'Gói hiện tại',
          price: 0,
          currency: 'VND',
          duration_days: 30,
          max_job_posts: 0,
          max_candidate_searches: 0,
          max_ai_features: candidateSnapshot.max_ai_features,
          plan_audience: 'candidate',
          is_free: false,
          is_active: true,
        } as RecruitmentPlanRead)
      )
    }

    if (
      isSubscriptionLoading ||
      subscriptionError ||
      !activeSubscription
    ) {
      return null
    }

    if (activeSubscription.status !== 'active') {
      return null
    }

    if (activeSubscription.expires_at) {
      const expiresAt = new Date(activeSubscription.expires_at).getTime()

      if (Number.isNaN(expiresAt) || expiresAt <= Date.now()) {
        return null
      }
    }

    return (
      plans.find((plan) => plan.id === activeSubscription.plan_id) ||
      activeSubscription.plan ||
      null
    )
  }, [
    activeSubscription,
    candidateEntitlement.error,
    candidateEntitlement.isLoading,
    candidateIsPaid,
    candidateSnapshot,
    isCandidate,
    isSubscriptionLoading,
    plans,
    subscriptionError,
  ])

  const isLowerTierPlan = useCallback(
    (plan: RecruitmentPlanRead): boolean => {
      if (plan.is_free) {
        return false
      }

      if (!currentPlan || plan.id === currentPlan.id) {
        return false
      }

      if (
        typeof plan.price !== 'number' ||
        typeof currentPlan.price !== 'number' ||
        Number.isNaN(plan.price) ||
        Number.isNaN(currentPlan.price)
      ) {
        return false
      }

      const planCurrency = (plan.currency || 'VND').trim().toUpperCase()
      const currentCurrency = (currentPlan.currency || 'VND').trim().toUpperCase()

      if (planCurrency !== currentCurrency) {
        return false
      }

      return plan.price < currentPlan.price
    },
    [currentPlan],
  )

  const isUpgradePlan = useCallback(
    (plan: RecruitmentPlanRead): boolean => {
      if (plan.is_free) {
        return false
      }

      if (!currentPlan || plan.id === currentPlan.id) {
        return false
      }

      if (
        typeof plan.price !== 'number' ||
        typeof currentPlan.price !== 'number' ||
        Number.isNaN(plan.price) ||
        Number.isNaN(currentPlan.price)
      ) {
        return false
      }

      const planCurrency = (plan.currency || 'VND').trim().toUpperCase()
      const currentCurrency = (currentPlan.currency || 'VND').trim().toUpperCase()

      if (planCurrency !== currentCurrency) {
        return false
      }

      return plan.price > currentPlan.price
    },
    [currentPlan],
  )

  const isEqualPricePlan = useCallback(
    (plan: RecruitmentPlanRead): boolean => {
      if (plan.is_free) {
        return false
      }

      if (!currentPlan || plan.id === currentPlan.id) {
        return false
      }

      if (
        typeof plan.price !== 'number' ||
        typeof currentPlan.price !== 'number' ||
        Number.isNaN(plan.price) ||
        Number.isNaN(currentPlan.price)
      ) {
        return false
      }

      const planCurrency = (plan.currency || 'VND').trim().toUpperCase()
      const currentCurrency = (currentPlan.currency || 'VND').trim().toUpperCase()

      return planCurrency === currentCurrency && plan.price === currentPlan.price
    },
    [currentPlan],
  )

  const isDifferentCurrencyPlan = useCallback(
    (plan: RecruitmentPlanRead): boolean => {
      if (plan.is_free) {
        return false
      }

      if (!currentPlan || plan.id === currentPlan.id) {
        return false
      }

      const planCurrency = (plan.currency || 'VND').trim().toUpperCase()
      const currentCurrency = (currentPlan.currency || 'VND').trim().toUpperCase()

      return planCurrency !== currentCurrency
    },
    [currentPlan],
  )

  const isCandidateEntitlementBlocked =
    isCandidate &&
    (candidateEntitlement.isLoading || Boolean(candidateEntitlement.error))

  const handleSelectPlan = useCallback(
    (planId: string) => {
      if (isCurrentPlan(planId)) {
        return
      }
      if (isRecruiter && !canPurchase) {
        return
      }
      if (isCandidate && isCandidateEntitlementBlocked) {
        return
      }
      const plan = plans.find((candidate) => candidate.id === planId)
      if (isCandidate && plan?.is_free) {
        return
      }
      if (plan && isLowerTierPlan(plan)) {
        return
      }
      if (isCandidate && candidateIsPaid && currentPlan && plan) {
        if (isEqualPricePlan(plan) || isDifferentCurrencyPlan(plan)) {
          return
        }
      }
      navigate(`/checkout/${planId}`)
    },
    [
      canPurchase,
      candidateIsPaid,
      currentPlan,
      isCandidate,
      isCandidateEntitlementBlocked,
      isCurrentPlan,
      isDifferentCurrencyPlan,
      isEqualPricePlan,
      isLowerTierPlan,
      isRecruiter,
      navigate,
      plans,
    ],
  )

  const isPlanDisabled = useCallback(
    (plan: RecruitmentPlanRead): boolean => {
      if (isCandidate) {
        if (plan.is_free === true) {
          return true
        }
        if (isCandidateEntitlementBlocked) {
          return true
        }
        if (candidateIsPaid && currentPlan) {
          if (isCurrentPlan(plan.id)) {
            return true
          }
          if (isLowerTierPlan(plan)) {
            return true
          }
          if (isEqualPricePlan(plan)) {
            return true
          }
          if (isDifferentCurrencyPlan(plan)) {
            return true
          }
        }
        return false
      }
      return !canPurchase
    },
    [
      canPurchase,
      candidateIsPaid,
      currentPlan,
      isCandidate,
      isCandidateEntitlementBlocked,
      isCurrentPlan,
      isDifferentCurrencyPlan,
      isEqualPricePlan,
      isLowerTierPlan,
    ],
  )

  const disabledReason = useCallback(
    (plan: RecruitmentPlanRead): string | undefined => {
      if (isCandidate) {
        if (plan.is_free) {
          return 'Gói miễn phí không cần thanh toán'
        }
        if (isCandidateEntitlementBlocked) {
          return candidateEntitlement.error
            ? 'Không thể xác thực gói dịch vụ hiện tại. Vui lòng thử lại'
            : 'Đang tải thông tin gói dịch vụ...'
        }
        if (candidateIsPaid && currentPlan) {
          if (isCurrentPlan(plan.id)) {
            return 'Gói hiện tại của bạn'
          }
          if (isLowerTierPlan(plan)) {
            return 'Gói thấp hơn gói của bạn'
          }
          if (isEqualPricePlan(plan)) {
            return 'Gói có cùng mức giá với gói hiện tại của bạn'
          }
          if (isDifferentCurrencyPlan(plan)) {
            return 'Khác loại tiền tệ với gói hiện tại của bạn'
          }
        }
        return undefined
      }
      if (isRecruiter && !canPurchase) {
        return 'Chỉ Quản trị viên công ty (Workspace Admin) mới có quyền mua hoặc thay đổi gói dịch vụ.'
      }
      return undefined
    },
    [
      canPurchase,
      candidateEntitlement.error,
      candidateIsPaid,
      currentPlan,
      isCandidate,
      isCandidateEntitlementBlocked,
      isCurrentPlan,
      isDifferentCurrencyPlan,
      isEqualPricePlan,
      isLowerTierPlan,
      isRecruiter,
    ],
  )

  const renderPlanSkeleton = () => (
    <article className="flex flex-col border rounded-xl p-5" data-testid="skeleton">
      <div className="flex-1 flex flex-col">
        <Skeleton className="h-6 w-3/4 mb-4 rounded" />
        <Skeleton className="h-4 w-full mb-2 rounded" />
        <Skeleton className="h-4 w-2/3 rounded" />
        <div className="mt-4 space-y-2">
          <Skeleton className="h-8 w-1/2 rounded" />
          <Skeleton className="h-4 w-1/3 rounded" />
          <Skeleton className="h-4 w-1/2 rounded" />
        </div>
        <Skeleton className="h-4 w-full mt-4 rounded" />
        <Skeleton className="h-4 w-2/3 rounded" />
      </div>
      <Skeleton className="h-10 w-full mt-4 rounded-lg" />
    </article>
  )

  return (
    <div className="container py-10 sm:py-12">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <h1 className="font-display text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            {isCandidate ? 'Gói dịch vụ AI' : 'Các gói tuyển dụng'}
          </h1>
          <p className="mt-2 max-w-2xl text-base text-muted-foreground sm:text-lg">
            {isCandidate
              ? 'Chọn gói AI phù hợp để phân tích CV, gợi ý việc làm và trò chuyện với trợ lý AI.'
              : 'Chọn gói phù hợp để đăng tin tuyển dụng và tìm ứng viên tốt nhất cho doanh nghiệp của bạn.'}
          </p>
        </header>

        {isCandidate && candidateSnapshot ? (
          <div
            role="status"
            className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/70 bg-card px-4 py-3"
          >
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant={candidateIsPaid ? 'ai-gradient' : 'outline-ai'}>
                {candidateIsPaid ? 'Gói trả phí' : 'Gói miễn phí'}
              </Badge>
              <span className="font-medium text-foreground">
                {candidateSnapshot.plan_name ?? 'Gói hiện tại'}
              </span>
              <span className="text-muted-foreground">
                · {candidateSnapshot.ai_features_used}/
                {candidateSnapshot.max_ai_features} lượt AI
              </span>
            </div>
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Lượt AI dùng chung cho các tính năng hỗ trợ
            </span>
          </div>
        ) : null}

        {isRecruiter && activeSubscription && (
          <CurrentSubscriptionCard
            subscription={activeSubscription}
            plans={plans}
            onRenew={() => companySubscription.refetch()}
          />
        )}

        <div className="mt-8">
          {isRecruiter && !canPurchase ? (
            <div
              role="note"
              className="mb-5 rounded-xl border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground"
            >
              Chỉ Quản trị viên công ty (Workspace Admin) mới có quyền mua hoặc
              thay đổi gói dịch vụ.
            </div>
          ) : null}
          {isLoading ? (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              {[1, 2].map((i) => (
                <div key={i}>{renderPlanSkeleton()}</div>
              ))}
            </div>
          ) : plans.length === 0 ? (
            <EmptyState
              title={
                isCandidate
                  ? 'Không có gói dịch vụ AI'
                  : 'Không có gói tuyển dụng'
              }
              description={
                isCandidate
                  ? 'Hiện không có gói AI nào khả dụng. Hãy thử lại sau hoặc liên hệ hỗ trợ.'
                  : 'Hiện không có gói đăng tin tuyển dụng nào khả dụng. Hãy thử lại sau hoặc liên hệ hỗ trợ.'
              }
            />
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              {plans.map((plan) => (
                <PlanCard
                  key={plan.id}
                  plan={plan}
                  isCurrent={isCurrentPlan(plan.id)}
                  isLowerTier={isLowerTierPlan(plan)}
                  isUpgrade={isCandidate && candidateIsPaid ? isUpgradePlan(plan) : false}
                  onSelect={handleSelectPlan}
                  disabled={isPlanDisabled(plan)}
                  disabledReason={disabledReason(plan)}
                />
              ))}
            </div>
          )}

          {error && !isLoading && (
            <ErrorBanner
              message={error}
              onRetry={refetch}
              className="mt-6"
            />
          )}

          {isCandidate && candidateEntitlement.error ? (
            <ErrorBanner
              message={candidateEntitlement.error}
              onRetry={candidateEntitlement.refetch}
              className="mt-6"
            />
          ) : null}
        </div>
      </div>
    </div>
  )
}

PlansPage.displayName = 'PlansPage'

export default PlansPage
