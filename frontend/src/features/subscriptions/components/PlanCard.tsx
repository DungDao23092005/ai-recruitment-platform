import * as React from 'react'
import { cn } from '@/utils/cn'
import { Button } from '@/components/ui/button'
import type { RecruitmentPlanRead } from '@/types/subscription'

export interface PlanCardProps {
  plan: RecruitmentPlanRead
  onSelect: (planId: string) => void
  isSelected?: boolean
  className?: string
}

const PlanCard = React.forwardRef<HTMLDivElement, PlanCardProps>(
  ({ plan, onSelect, isSelected = false, className }, ref) => (
<div
        ref={ref}
        role="article"
        className={cn(
          'border rounded-lg hover:border-primary transition-colors cursor-pointer',
          isSelected && 'bg-primary/5 border-primary',
          className,
        )}
        onClick={() => onSelect(plan.id)}
        aria-label={`Xem chi tiết gói ${plan.name}`}
      >
      <div className="p-5">
        <h3 className="font-semibold leading-none tracking-tick">{plan.name}</h3>
        <p className="text-sm text-muted-foreground line-clamp-3">{plan.description}</p>
        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-lg font-medium">{plan.price.toLocaleString()} {plan.currency}</span>
          <span className="text-xs text-muted-foreground">{plan.duration_days} ngày</span>
        </div>
        {plan.features && plan.features.length > 0 && (
          <div className="mt-3 text-xs text-muted-foreground line-clamp-3">
            {plan.features.map((feature, idx) => (
              <span key={idx} className="block mb-1">
                • {feature}
              </span>
            ))}
          </div>
        )}
        <Button
          variant="outline"
          size="sm"
          className="mt-3 w-full"
          onClick={(e) => {
            e.stopPropagation()
            onSelect(plan.id)
          }}
        >
          Chọn gói
        </Button>
      </div>
    </div>
  ),
)
PlanCard.displayName = 'PlanCard'

export { PlanCard }