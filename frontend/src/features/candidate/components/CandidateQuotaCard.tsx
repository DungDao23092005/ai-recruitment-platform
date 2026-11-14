import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import type { CandidateEntitlementSummary } from '@/types/subscription'

export interface CandidateQuotaCardProps {
  entitlement: CandidateEntitlementSummary | null
  isLoading?: boolean
  error?: string | null
  onRetry?: () => void
  upgradeHref?: string
}

const FREE_RESET_LABEL = 'Làm mới vào ngày 01 hằng tháng'
const FREE_PRESERVED_MESSAGE =
  'Gói miễn phí được bảo lưu và sẽ tự động tiếp tục khi gói trả phí hết hạn.'

function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)
}

export function CandidateQuotaCard({
  entitlement,
  isLoading = false,
  error = null,
  onRetry,
  upgradeHref = '/plans',
}: CandidateQuotaCardProps) {
  return (
    <Card className="border-border/70">
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="font-display text-lg font-semibold">
            Gói dịch vụ AI
          </CardTitle>
          {entitlement ? (
            <Badge
              variant={
                entitlement.effective_tier === 'paid'
                  ? 'ai-gradient'
                  : 'outline-ai'
              }
            >
              {entitlement.effective_tier === 'paid'
                ? 'Gói trả phí'
                : 'Gói miễn phí'}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <ErrorBanner message={error} onRetry={onRetry} />
        ) : isLoading ? (
          <div className="space-y-3" data-testid="candidate-quota-loading">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-2 w-full" />
            <Skeleton className="h-4 w-56" />
          </div>
        ) : !entitlement ? (
          <EmptyState
            title="Chưa có thông tin gói AI"
            description="Hệ thống chưa tải được quyền lợi AI của bạn. Vui lòng thử lại."
          >
            <Button type="button" variant="outline" onClick={onRetry}>
              Thử lại
            </Button>
          </EmptyState>
        ) : (
          <CandidateQuotaContent
            entitlement={entitlement}
            upgradeHref={upgradeHref}
          />
        )}
      </CardContent>
    </Card>
  )
}

function CandidateQuotaContent({
  entitlement,
  upgradeHref,
}: {
  entitlement: CandidateEntitlementSummary
  upgradeHref: string
}) {
  const snapshot = entitlement.effective_subscription
  const limit = Math.max(0, snapshot.max_ai_features)
  const used = Math.max(0, snapshot.ai_features_used)
  const remaining = Math.max(0, snapshot.ai_features_remaining)
  const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0
  const isPaid = entitlement.effective_tier === 'paid'
  const isExhausted = isPaid
    ? entitlement.is_paid_exhausted
    : remaining <= 0

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">
            {snapshot.plan_name ?? (isPaid ? 'Gói trả phí' : 'Gói miễn phí')}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {isPaid && snapshot.expires_at
              ? `Hết hạn ${formatDateTime(snapshot.expires_at)}`
              : FREE_RESET_LABEL}
          </p>
        </div>
        <p className="text-sm font-semibold text-foreground">
          {used}/{limit}
        </p>
      </div>

      <Progress
        value={percent}
        variant={
          isExhausted ? 'danger' : percent >= 80 ? 'warning' : 'ai'
        }
        aria-label="Mức sử dụng lượt AI"
      />

      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-border/70 bg-muted/30 px-4 py-3">
          <dt className="text-xs font-medium text-muted-foreground">
            Lượt AI đã sử dụng
          </dt>
          <dd className="mt-1 font-display text-xl font-semibold text-foreground">
            {used}
          </dd>
        </div>
        <div className="rounded-xl border border-border/70 bg-muted/30 px-4 py-3">
          <dt className="text-xs font-medium text-muted-foreground">
            Lượt AI còn lại
          </dt>
          <dd className="mt-1 font-display text-xl font-semibold text-foreground">
            {remaining}
          </dd>
        </div>
      </dl>

      {isPaid ? (
        <p className="rounded-xl border border-border/70 bg-background px-4 py-3 text-xs text-muted-foreground">
          {FREE_PRESERVED_MESSAGE}
        </p>
      ) : entitlement.is_projected ? (
        <p className="text-xs text-muted-foreground">
          Hạn mức đã được làm mới cho tháng này và sẽ áp dụng cho lượt AI tiếp
          theo.
        </p>
      ) : null}

      {isExhausted ? (
        <div className="rounded-xl border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-foreground">
          Bạn đã dùng hết lượt AI của gói hiện tại.
          {isPaid
            ? ' Vui lòng gia hạn gói để tiếp tục sử dụng.'
            : ' Hạn mức sẽ được làm mới vào tháng sau.'}
        </div>
      ) : null}

      <Link to={upgradeHref} className="inline-flex">
        <Button variant={isPaid ? 'outline' : 'default'}>
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Nâng cấp gói AI
        </Button>
      </Link>
    </div>
  )
}
