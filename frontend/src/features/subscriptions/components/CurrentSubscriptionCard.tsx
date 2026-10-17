import * as React from 'react'
import { cn } from '@/utils/cn'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { AlertCircle, Calendar, Package } from 'lucide-react'
import type { RecruitmentPlan, Subscription } from '@/types/subscription'

export interface CurrentSubscriptionCardProps {
  subscription: Subscription | null
  plans?: RecruitmentPlan[]
  onRenew?: () => void
  className?: string
}

function formatDate(dateString: string | null): string {
  if (!dateString) return 'Chưa xác định'
  try {
    const date = new Date(dateString)
    if (isNaN(date.getTime())) return 'Không hợp lệ'
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(date)
  } catch {
    return 'Không hợp lệ'
  }
}

function getStatusInfo(status: string): { label: string; variant: 'success' | 'destructive' | 'neutral' | 'warning'; icon: React.ReactNode } {
  switch (status) {
    case 'active':
      return {
        label: 'Đang hoạt động',
        variant: 'success',
        icon: <Package className="h-3.5 w-3.5" />,
      }
    case 'pending':
      return {
        label: 'Chờ duyệt',
        variant: 'warning',
        icon: <AlertCircle className="h-3.5 w-3.5" />,
      }
    case 'cancelled':
      return {
        label: 'Đã hủy',
        variant: 'destructive',
        icon: <AlertCircle className="h-3.5 w-3.5" />,
      }
    case 'expired':
      return {
        label: 'Hết hạn',
        variant: 'neutral',
        icon: <Calendar className="h-3.5 w-3.5" />,
      }
    default:
      return {
        label: status,
        variant: 'neutral',
        icon: <Package className="h-3.5 w-3.5" />,
      }
  }
}

const CurrentSubscriptionCard = React.forwardRef<HTMLDivElement, CurrentSubscriptionCardProps>(
  ({ subscription, plans, onRenew, className }, ref) => {
    if (!subscription) {
      return null
    }

    // Prefer the plan embedded in the subscription API response; fall back to
    // resolving plan_id against already-loaded plans before giving up.
    const plan =
      subscription.plan ??
      plans?.find((candidate) => candidate.id === subscription.plan_id) ??
      null
    const planName = plan?.name || 'Gói không xác định'
    const planDuration = plan?.duration_days
    const { label: statusLabel, variant: statusVariant, icon: statusIcon } = getStatusInfo(subscription.status)
    const isActive = subscription.status === 'active'
    const expiresAt = subscription.expires_at
    const isExpired = expiresAt ? new Date(expiresAt) < new Date() : false

    return (
      <div
        ref={ref}
        className={cn(
          'border rounded-xl p-4 mb-6',
          isActive
            ? 'border-green-200 bg-green-50/50'
            : 'border-amber-200 bg-amber-50/50',
          className,
        )}
      >
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3 flex-1">
            <div className="flex-shrink-0 p-2 rounded-lg bg-white border">
              {statusIcon}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <Badge
                  variant={statusVariant}
                  className="px-2.5 py-1 text-xs font-medium rounded-full"
                >
                  {statusLabel}
                </Badge>
                <span className="font-medium text-sm text-foreground">
                  {planName}
                </span>
              </div>
              {planDuration && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Thời hạn: {planDuration} ngày
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 w-full sm:w-auto">
            {expiresAt && (
              <div className={cn(
                'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full',
                isExpired ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
              )}>
                <Calendar className="h-3 w-3" />
                <span>
                  {isExpired ? 'Hết hạn' : 'Hết hạn vào'} {formatDate(expiresAt)}
                </span>
              </div>
            )}

            {isActive && onRenew && (
              <Button
                variant="outline"
                size="sm"
                className="w-full sm:w-auto"
                onClick={onRenew}
              >
                Làm mới trạng thái
              </Button>
            )}

            {isActive && !onRenew && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-3 py-1.5 rounded-full bg-gray-100">
                <AlertCircle className="h-3 w-3" />
                <span>Hệ thống chưa hỗ trợ đăng ký chồng gói</span>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  },
)
CurrentSubscriptionCard.displayName = 'CurrentSubscriptionCard'

export { CurrentSubscriptionCard }