import * as React from 'react'
import { cn } from '@/utils/cn'
import { Button } from '@/components/ui/button'
import type { RecruitmentPlanRead } from '@/types/subscription'

export interface PlanCardProps {
  plan: RecruitmentPlanRead
  onSelect: (planId: string) => void
  isSelected?: boolean
  isCurrent?: boolean
  className?: string
}

function formatPrice(price: number, currency: string): string {
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(price)
}

function formatDuration(days: number): string {
  if (days >= 365) {
    const years = Math.floor(days / 365)
    return `${years} năm`
  }
  if (days >= 30) {
    const months = Math.floor(days / 30)
    return `${months} tháng`
  }
  return `${days} ngày`
}

const PlanCard = React.forwardRef<HTMLDivElement, PlanCardProps>(
  ({ plan, onSelect, isSelected = false, isCurrent = false, className }, ref) => {
    const isDisabled = isCurrent || isSelected
    const buttonLabel = isCurrent
      ? 'Gói hiện tại của bạn'
      : isSelected
        ? 'Đã chọn'
        : 'Chọn gói này'
    const buttonAriaLabel = isCurrent
      ? `Gói hiện tại của bạn: ${plan.name}`
      : isSelected
        ? `Đã chọn gói ${plan.name}`
        : `Chọn gói ${plan.name}`

    return (
      <article
        ref={ref}
        className={cn(
          'flex flex-col border rounded-xl p-5 transition-all duration-200',
          'hover:border-primary/50 hover:shadow-lg',
          isSelected && 'border-primary bg-primary/5 ring-1 ring-primary/20',
          !isSelected && isCurrent && 'border-primary/60 bg-primary/5',
          className,
        )}
      >
        <div className="flex-1 flex flex-col">
          <header className="mb-4">
            <h3 className="text-lg font-semibold text-foreground leading-snug">
              {plan.name}
            </h3>
          </header>

          <div className="mb-4 space-y-2 text-sm">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-foreground">
                {formatPrice(plan.price, plan.currency)}
              </span>
              <span className="text-muted-foreground">
                / {formatDuration(plan.duration_days)}
              </span>
            </div>

            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="font-medium">{plan.max_job_posts}</span>
              <span>bài đăng tin</span>
            </div>

            {plan.max_candidate_searches !== null && plan.max_candidate_searches !== undefined && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <span className="font-medium">{plan.max_candidate_searches}</span>
                <span>tìm kiếm ứng viên</span>
              </div>
            )}

            {plan.max_ai_features !== null && plan.max_ai_features !== undefined && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <span className="font-medium">{plan.max_ai_features}</span>
                <span>tính năng AI</span>
              </div>
            )}
          </div>

          {plan.features && plan.features.length > 0 && (
            <div className="mb-4 text-xs text-muted-foreground line-clamp-3">
              {plan.features.map((feature, idx) => (
                <span key={idx} className="block mb-1">
                  • {feature}
                </span>
              ))}
            </div>
          )}
        </div>

        <Button
          variant={isSelected ? 'default' : 'outline'}
          size="sm"
          className="mt-4 w-full"
          onClick={(e) => {
            e.stopPropagation()
            if (isDisabled) {
              return
            }
            onSelect(plan.id)
          }}
          disabled={isDisabled}
          aria-pressed={isSelected}
          aria-label={buttonAriaLabel}
        >
          {buttonLabel}
        </Button>
      </article>
    )
  },
)
PlanCard.displayName = 'PlanCard'

export { PlanCard }