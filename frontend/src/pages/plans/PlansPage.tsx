import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Archive, Bot, Briefcase, Sparkles } from 'lucide-react'
import { usePlans } from '@/features/subscriptions/hooks/usePlans'
import { useMySubscription } from '@/features/subscriptions/hooks/useMySubscription'
import { PlanCard } from '@/features/subscriptions/components/PlanCard'
import { CurrentSubscriptionCard } from '@/features/subscriptions/components/CurrentSubscriptionCard'
import { RecruiterTransitionModal } from '@/features/subscriptions/components/RecruiterTransitionModal'
import { useAuth } from '@/contexts/AuthContext'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { cn } from '@/utils/cn'
import type { RecruitmentPlanRead } from '@/types/subscription'

const HERO_BENEFITS = [
  {
    icon: Briefcase,
    title: 'Đăng tin tuyển dụng',
    description: 'Đăng tin theo hạn mức của gói bạn chọn.',
  },
  {
    icon: Bot,
    title: 'Tìm kiếm ứng viên bằng AI',
    description: 'Tìm ứng viên phù hợp trong phạm vi gói.',
  },
  {
    icon: Archive,
    title: 'Dữ liệu hồ sơ được lưu giữ',
    description: 'Hồ sơ, CV và lịch sử ứng tuyển vẫn được giữ lại.',
  },
] as const

function CandidateUpgradeHero() {
  return (
    <section className="relative overflow-hidden rounded-2xl border bg-card shadow-soft">
      <div className="ai-gradient absolute inset-x-0 top-0 h-1" aria-hidden="true" />
      <div className="grid gap-8 p-6 sm:p-10 lg:grid-cols-[1.15fr_1fr] lg:items-center">
        <div>
          <Badge variant="outline-ai" className="gap-1.5 px-2.5 py-1">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Dành cho ứng viên
          </Badge>
          <h1 className="mt-4 font-display text-3xl font-bold leading-tight tracking-tight text-foreground sm:text-4xl">
            Bạn muốn trở thành <span className="ai-text">nhà tuyển dụng</span>?
          </h1>
          <p className="mt-3 text-base font-medium text-foreground">
            Tìm đúng người. Xây dựng đội ngũ. Phát triển doanh nghiệp.
          </p>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">
            Khám phá công cụ tuyển dụng thông minh với AI để đăng tin và tìm ứng
            viên. Quyền lợi nhà tuyển dụng chỉ được kích hoạt sau khi hệ thống
            xác minh thanh toán thành công.
          </p>
        </div>
        <ul className="space-y-3">
          {HERO_BENEFITS.map(({ icon: Icon, title, description }) => (
            <li
              key={title}
              className="flex items-start gap-3 rounded-xl border border-border/70 bg-background p-3.5"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">{title}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {description}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

export function PlansPage() {
  const { plans, isLoading, error, refetch } = usePlans()
  const {
    subscription: activeSubscription,
    isLoading: isSubscriptionLoading,
    error: subscriptionError,
    refetch: refetchSub,
  } = useMySubscription()
  const { currentUser } = useAuth()
  const navigate = useNavigate()

  const isCandidate = currentUser?.role === 'candidate'

  const [pendingPlan, setPendingPlan] = useState<RecruitmentPlanRead | null>(
    null,
  )
  // Guards against firing a second navigation if the CTA is activated twice
  // before the modal unmounts.
  const navigatingRef = useRef(false)

  const isCurrentPlan = useCallback(
    (planId: string): boolean => {
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
    [activeSubscription, isSubscriptionLoading, subscriptionError],
  )

  // Only surface a confirmation for a plan that is still present in the
  // freshly-loaded plan list, so a stale selection can never be confirmed.
  const isPendingPlanAvailable = useMemo(
    () =>
      pendingPlan !== null &&
      plans.some((plan) => plan.id === pendingPlan.id),
    [pendingPlan, plans],
  )
  const showTransitionModal = isCandidate && isPendingPlanAvailable

  const handleSelectPlan = useCallback(
    (planId: string) => {
      if (isCurrentPlan(planId)) {
        return
      }
      if (isCandidate) {
        const plan = plans.find((candidate) => candidate.id === planId)
        if (!plan) {
          return
        }
        navigatingRef.current = false
        setPendingPlan(plan)
        return
      }
      navigate(`/checkout/${planId}`)
    },
    [isCandidate, isCurrentPlan, navigate, plans],
  )

  const handleCancelTransition = useCallback(() => {
    navigatingRef.current = false
    setPendingPlan(null)
  }, [])

  const handleConfirmTransition = useCallback(() => {
    if (!pendingPlan || navigatingRef.current) {
      return
    }
    if (!plans.some((plan) => plan.id === pendingPlan.id)) {
      setPendingPlan(null)
      return
    }
    navigatingRef.current = true
    const planId = pendingPlan.id
    setPendingPlan(null)
    navigate(`/checkout/${planId}`)
  }, [navigate, pendingPlan, plans])

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
        {isCandidate ? <CandidateUpgradeHero /> : null}

        {/* Page Header */}
        <header className={cn('mb-8', isCandidate && 'mt-12')}>
          {isCandidate ? (
            <h2 className="font-display text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              Các gói tuyển dụng
            </h2>
          ) : (
            <h1 className="font-display text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Các gói tuyển dụng
            </h1>
          )}
          <p className="mt-2 max-w-2xl text-base text-muted-foreground sm:text-lg">
            Chọn gói phù hợp để đăng tin tuyển dụng và tìm ứng viên tốt nhất cho doanh nghiệp của bạn.
          </p>
        </header>

        {/* Current Subscription Card */}
        {activeSubscription && (
          <CurrentSubscriptionCard
            subscription={activeSubscription}
            plans={plans}
            onRenew={() => refetchSub()}
          />
        )}

        {/* Plans Grid */}
        <div className="mt-8">
          {isLoading ? (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              {[1, 2].map((i) => (
                <div key={i}>{renderPlanSkeleton()}</div>
              ))}
            </div>
          ) : plans.length === 0 ? (
            <EmptyState
              title="Không có gói tuyển dụng"
              description="Hiện không có gói đăng tin tuyển dụng nào khả dụng. Hãy thử lại sau hoặc liên hệ hỗ trợ."
            />
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              {plans.map((plan) => (
                <PlanCard
                  key={plan.id}
                  plan={plan}
                  isCurrent={isCurrentPlan(plan.id)}
                  onSelect={handleSelectPlan}
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
        </div>
      </div>

      {showTransitionModal && pendingPlan ? (
        <RecruiterTransitionModal
          plan={pendingPlan}
          onClose={handleCancelTransition}
          onConfirm={handleConfirmTransition}
        />
      ) : null}
    </div>
  )
}

PlansPage.displayName = 'PlansPage'

export default PlansPage
