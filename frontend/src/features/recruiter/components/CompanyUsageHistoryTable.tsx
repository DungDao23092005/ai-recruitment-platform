import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Skeleton } from '@/components/ui/skeleton'
import type {
  CompanyUsageItem,
  SubscriptionUsageStatus,
} from '@/types/subscription'

export interface CompanyUsageHistoryTableProps {
  items: CompanyUsageItem[]
  isLoading?: boolean
  error?: string | null
  onRetry?: () => void
}

const STATUS_VARIANTS: Record<
  SubscriptionUsageStatus,
  'success' | 'warning' | 'destructive'
> = {
  reserved: 'warning',
  completed: 'success',
  failed: 'destructive',
}

function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Không hợp lệ'
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)
}

function formatAmount(value: number): string {
  return value.toLocaleString('vi-VN')
}

export function CompanyUsageHistoryTable({
  items,
  isLoading = false,
  error = null,
  onRetry,
}: CompanyUsageHistoryTableProps) {
  return (
    <Card className="border-border/70">
      <CardHeader>
        <CardTitle className="font-display text-lg font-semibold">
          Lịch sử sử dụng
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <ErrorBanner message={error} onRetry={onRetry} />
        ) : isLoading ? (
          <div className="space-y-3" data-testid="company-usage-loading">
            {[1, 2, 3, 4].map((item) => (
              <Skeleton key={item} className="h-10 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            title="Chưa có lịch sử sử dụng"
            description="Chưa có lượt sử dụng nào trong khoảng thời gian đã chọn."
          />
        ) : (
          <div className="-mx-6 overflow-x-auto px-6">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <th className="pb-3 pr-4 font-semibold">Thời gian</th>
                  <th className="pb-3 pr-4 font-semibold">Thành viên</th>
                  <th className="pb-3 pr-4 font-semibold">Tính năng</th>
                  <th className="pb-3 pr-4 text-right font-semibold">Số lượng</th>
                  <th className="pb-3 font-semibold">Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const statusVariant =
                    STATUS_VARIANTS[item.status] ?? 'neutral'
                  return (
                    <tr
                      key={item.id}
                      className="border-b border-border/60 last:border-0"
                    >
                      <td className="whitespace-nowrap py-3 pr-4 text-muted-foreground">
                        {formatDateTime(item.created_at)}
                      </td>
                      <td className="py-3 pr-4">
                        <p className="font-medium text-foreground">
                          {item.user_full_name || item.user_email || 'Không xác định'}
                        </p>
                        {item.user_full_name && item.user_email ? (
                          <p className="text-xs text-muted-foreground">
                            {item.user_email}
                          </p>
                        ) : null}
                      </td>
                      <td className="py-3 pr-4 text-foreground">
                        {item.feature_label}
                      </td>
                      <td className="py-3 pr-4 text-right font-medium text-foreground">
                        {formatAmount(item.amount)}
                      </td>
                      <td className="py-3">
                        <Badge variant={statusVariant}>
                          {item.status_label}
                        </Badge>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
