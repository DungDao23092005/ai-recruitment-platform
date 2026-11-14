import { Link } from 'react-router-dom'
import { CalendarDays, CreditCard, Package } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/utils/cn'
import type { Subscription, SubscriptionStatus } from '@/types/subscription'

export interface CompanySubscriptionCardProps {
  subscription: Subscription | null
  isLoading?: boolean
  error?: string | null
  onRetry?: () => void
  isAdmin?: boolean
  className?: string
}

const STATUS_INFO: Record<
  SubscriptionStatus,
  {
    label: string
    variant: 'success' | 'warning' | 'destructive' | 'neutral'
  }
> = {
  active: { label: 'Đang hoạt động', variant: 'success' },
  pending: { label: 'Chờ duyệt', variant: 'warning' },
  cancelled: { label: 'Đã hủy', variant: 'destructive' },
  expired: { label: 'Hết hạn', variant: 'neutral' },
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Chưa xác định'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Không hợp lệ'
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)
}

function formatNumber(value: number): string {
  return value.toLocaleString('vi-VN')
}

interface QuotaRowProps {
  label: string
  maximum?: number | null
  used?: number | null
}

function QuotaRow({ label, maximum, used }: QuotaRowProps) {
  const hasMaximum = typeof maximum === 'number' && maximum > 0
  const isUnlimited = maximum === null
  const usedValue = typeof used === 'number' ? used : null
  const remaining =
    hasMaximum && usedValue !== null ? Math.max(0, maximum - usedValue) : null
  const percentage =
    hasMaximum && usedValue !== null
      ? Math.min(100, Math.max(0, (usedValue / maximum) * 100))
      : 0

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-foreground">{label}</span>
        <span className="text-muted-foreground">
          {isUnlimited
            ? 'Không giới hạn'
            : hasMaximum
              ? `${formatNumber(usedValue ?? 0)} / ${formatNumber(maximum)}`
              : usedValue !== null
                ? `${formatNumber(usedValue)} đã dùng`
                : '—'}
        </span>
      </div>
      <Progress
        value={percentage}
        variant={percentage >= 90 ? 'warning' : 'primary'}
        className="h-1.5"
        aria-label={`${label}: đã dùng ${percentage.toFixed(0)}%`}
      />
      {remaining !== null ? (
        <p className="text-xs text-muted-foreground">
          Còn lại {formatNumber(remaining)}
        </p>
      ) : null}
    </div>
  )
}

export function CompanySubscriptionCard({
  subscription,
  isLoading = false,
  error = null,
  onRetry,
  isAdmin = false,
  className,
}: CompanySubscriptionCardProps) {
  if (isLoading) {
    return (
      <Card className={cn('border-border/70', className)} data-testid="company-subscription-loading">
        <CardHeader className="gap-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-3 w-4/6" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className={cn('border-border/70', className)}>
        <CardContent className="p-4">
          <ErrorBanner
            message={error}
            onRetry={onRetry}
          />
        </CardContent>
      </Card>
    )
  }

  if (!subscription) {
    return (
      <Card className={cn('border-border/70', className)}>
        <CardHeader className="gap-2">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <Package className="h-4 w-4" aria-hidden="true" />
            </span>
            <CardTitle className="font-display text-lg font-semibold">
              Chưa có gói dịch vụ
            </CardTitle>
          </div>
          <CardDescription>
            Công ty chưa có gói tuyển dụng đang hoạt động.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isAdmin ? (
            <Link to="/plans?audience=company">
              <Button>
                <CreditCard className="h-4 w-4" aria-hidden="true" />
                Chọn gói dịch vụ
              </Button>
            </Link>
          ) : (
            <p className="text-sm text-muted-foreground">
              Liên hệ Quản trị viên công ty để chọn gói dịch vụ.
            </p>
          )}
        </CardContent>
      </Card>
    )
  }

  const statusInfo = STATUS_INFO[subscription.status] ?? {
    label: subscription.status,
    variant: 'neutral' as const,
  }
  const planName = subscription.plan?.name ?? 'Gói không xác định'

  return (
    <Card className={cn('border-border/70', className)}>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="font-display text-lg font-semibold">
                {planName}
              </CardTitle>
              <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
            </div>
            <CardDescription className="flex items-center gap-1.5">
              <CalendarDays className="h-3.5 w-3.5" aria-hidden="true" />
              Hết hạn vào {formatDate(subscription.expires_at)}
            </CardDescription>
          </div>
          <Link to="/recruiter/billing">
            <Button variant="outline" size="sm">
              Xem chi tiết
            </Button>
          </Link>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <QuotaRow
          label="Tin tuyển dụng"
          maximum={subscription.max_job_posts}
          used={subscription.job_posts_used}
        />
        <QuotaRow
          label="Tìm kiếm ứng viên"
          maximum={subscription.max_candidate_searches}
          used={subscription.candidate_searches_used}
        />
        <QuotaRow
          label="AI tuyển dụng"
          maximum={subscription.max_ai_features}
          used={subscription.ai_features_used}
        />
        {isAdmin ? (
          <div className="flex flex-wrap gap-2 border-t border-border pt-4">
            <Link to="/plans?audience=company">
              <Button size="sm" variant="outline">
                Gia hạn gói
              </Button>
            </Link>
            <Link to="/plans?audience=company">
              <Button size="sm" variant="outline">
                Thay đổi gói
              </Button>
            </Link>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
