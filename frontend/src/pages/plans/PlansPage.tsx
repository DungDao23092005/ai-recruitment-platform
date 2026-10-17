import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePlans } from '@/features/subscriptions/hooks/usePlans'
import { useMySubscription } from '@/features/subscriptions/hooks/useMySubscription'
import { PlanCard } from '@/features/subscriptions/components/PlanCard'
import { CurrentSubscriptionCard } from '@/features/subscriptions/components/CurrentSubscriptionCard'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'

export function PlansPage() {
  const { plans, isLoading, error, refetch } = usePlans()
  const { subscription: activeSubscription, refetch: refetchSub } = useMySubscription()
  const navigate = useNavigate()

  const handleSelectPlan = useCallback(
    (planId: string) => {
      navigate(`/checkout/${planId}`)
    },
    [navigate],
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
      <div className="max-w-7xl mx-auto">
        {/* Page Header */}
        <header className="mb-10">
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-foreground">
            Các gói tuyển dụng
          </h1>
          <p className="mt-2 text-lg text-muted-foreground">
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
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <div key={i}>{renderPlanSkeleton()}</div>
              ))}
            </div>
          ) : plans.length === 0 ? (
            <EmptyState
              title="Không có gói tuyển dụng"
              description="Hiện không có gói đăng tin tuyển dụng nào khả dụng. Hãy thử lại sau hoặc liên hệ hỗ trợ."
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {plans.map((plan) => (
                <PlanCard
                  key={plan.id}
                  plan={plan}
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
    </div>
  )
}

PlansPage.displayName = 'PlansPage'

export default PlansPage