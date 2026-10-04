import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePlans } from '@/features/subscriptions/hooks/usePlans'
import { useMySubscription } from '@/features/subscriptions/hooks/useMySubscription'
import { PlanCard } from '@/features/subscriptions/components/PlanCard'
import { CurrentSubscriptionCard } from '@/features/subscriptions/components/CurrentSubscriptionCard'
import { Spinner } from '@/components/ui/spinner'
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

  // Error state for plans
  if (error && !isLoading) {
    return (
      <ErrorBanner
        message={error}
        onRetry={refetch}
        className="mt-6"
      />
    )
  }

  return (
    <div className="container py-10 sm:py-12">
      <div className="max-w-7xl mx-auto">

        {/* Current Subscription Card */}
        <CurrentSubscriptionCard
          subscription={activeSubscription}
          onRenew={() => refetchSub()}
        />

        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {isLoading ? (
            <div className="h-64"/>
          ) : plans.length === 0 ? (
            <EmptyState
              title="Không có gói lên kế hoạch"
              description="Hiện không có gói đăng tin tuyển dụng nào khả dụng. Hãy thử lại sau hoặc liên hệ hỗ trợ."
            />
          ) : (
            plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                onSelect={handleSelectPlan}
              />
            ))
          )}
        </div>

        {isLoading && (
          <div className="mt-6">
            <Spinner className="h-6 w-6 mx-auto" />
            <span className="ml-2 text-sm text-muted-foreground">Đang tải gói...</span>
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
  )
}

PlansPage.displayName = 'PlansPage'

export default PlansPage