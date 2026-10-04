import * as React from 'react'
import { cn } from '@/utils/cn'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Subscription } from '@/types/subscription'

export interface CurrentSubscriptionCardProps {
  subscription: Subscription | null
  onRenew?: () => void
  className?: string
}

const CurrentSubscriptionCard = React.forwardRef<HTMLDivElement, CurrentSubscriptionCardProps>(
  ({ subscription, onRenew, className }, ref) => {
    if (!subscription) {
      return null
    }

    const plan = subscription.plan || { name: 'Gói dịch vụ' } as any
    const isActive = subscription.status === 'active'
    const statusLabel = isActive ? 'Đang active' : subscription.status

    return (
      <div
        ref={ref}
        className={cn(
          'border rounded-lg border-green-100 bg-green-50/30 pb-4',
          className,
        )}
      >
        <div className="p-4">
          <div className="flex items-center gap-3 mb-3">
            <Badge
              variant={isActive ? 'success' : 'neutral'}
              className={cn(
                'px-2 py-0.5 text-xs font-semibold rounded-full',
                isActive && 'bg-green-100 text-green-800',
                !isActive && 'bg-gray-100 text-gray-600',
              )}
            >
              {statusLabel}
            </Badge>
            <span className="font-medium text-sm">
              {plan.name}
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            {plan.duration_days || '30'} ngày
          </p>
          {isActive && onRenew && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 w-full text-sm"
              onClick={onRenew}
            >
              Tạo lại
            </Button>
          )}
        </div>
      </div>
    )
  },
)
CurrentSubscriptionCard.displayName = 'CurrentSubscriptionCard'

export { CurrentSubscriptionCard }