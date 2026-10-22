import * as React from 'react'
import { CheckCircle2 } from 'lucide-react'
import { cn } from '@/utils/cn'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { RecruitmentPlanRead } from '@/types/subscription'

export interface PlanCardProps {
  plan: RecruitmentPlanRead
  onSelect: (planId: string) => void
  isSelected?: boolean
  isCurrent?: boolean
  className?: string
}

export function formatPlanPrice(price: number, currency: string): string {
  try {
    return new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(price)
  } catch {
    return `${price.toLocaleString('vi-VN')} ${currency}`
  }
}

export function formatPlanDuration(days: number): string {
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
          'relative flex h-full flex-col rounded-2xl border bg-card p-6 shadow-soft transition-all duration-200',
          'hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-soft-lg',
          'focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2',
          isSelected && 'border-primary ring-2 ring-primary/30',
          !isSelected && isCurrent && 'border-primary/50 ring-1 ring-primary/20',
          className,
        )}
        aria-current={isCurrent ? 'true' : undefined}
      >
        {isCurrent ? (
          <Badge
            variant="outline-ai"
            className="absolute right-5 top-5 px-2.5 py-1 text-xs"
          >
            Gói của bạn
          </Badge>
        ) : null}

        <header className="flex-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            Gói tuyển dụng
          </p>
          <h3 className="mt-2 pr-16 text-xl font-semibold leading-snug text-foreground">
            {plan.name}
          </h3>
          {plan.description ? (
            <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
              {plan.description}
            </p>
          ) : null}

          <div className="mt-5 flex items-baseline gap-2">
            <span className="font-display text-3xl font-bold tracking-tight text-foreground">
              {formatPlanPrice(plan.price, plan.currency)}
            </span>
            <span className="text-sm text-muted-foreground">
              / {formatPlanDuration(plan.duration_days)}
            </span>
          </div>

          <dl className="mt-5 space-y-3 border-t border-border pt-5 text-sm">
            <div className="flex items-start gap-2.5">
              <CheckCircle2
                className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                aria-hidden="true"
              />
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <span className="font-semibold text-foreground">
                  {plan.max_job_posts}
                </span>
                <span>bài đăng tin</span>
              </div>
            </div>

            {plan.max_candidate_searches !== null &&
              plan.max_candidate_searches !== undefined && (
                <div className="flex items-start gap-2.5">
                  <CheckCircle2
                    className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                    aria-hidden="true"
                  />
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <span className="font-semibold text-foreground">
                      {plan.max_candidate_searches}
                    </span>
                    <span>tìm kiếm ứng viên</span>
                  </div>
                </div>
              )}

            {plan.max_ai_features !== null &&
              plan.max_ai_features !== undefined && (
                <div className="flex items-start gap-2.5">
                  <CheckCircle2
                    className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                    aria-hidden="true"
                  />
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <span className="font-semibold text-foreground">
                      {plan.max_ai_features}
                    </span>
                    <span>tính năng AI</span>
                  </div>
                </div>
              )}
          </dl>

          {plan.features && plan.features.length > 0 && (
            <ul className="mt-4 space-y-1.5 text-xs text-muted-foreground">
              {plan.features.slice(0, 4).map((feature, idx) => (
                <li key={idx} className="flex gap-2">
                  <span aria-hidden="true" className="text-primary">
                    •
                  </span>
                  <span>{feature}</span>
                </li>
              ))}
            </ul>
          )}
        </header>

        <Button
          variant={isSelected ? 'default' : isCurrent ? 'outline' : 'default'}
          size="lg"
          className="mt-6 w-full"
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
