import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Skeleton } from '@/components/ui/skeleton'
import type { PaymentOrderRead } from '@/types/payment'

export interface CompanyPaymentHistoryTableProps {
  orders: PaymentOrderRead[]
  isLoading?: boolean
  error?: string | null
  onRetry?: () => void
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Đang chờ',
  paid: 'Đã thanh toán',
  failed: 'Thất bại',
  expired: 'Hết hạn',
  cancelled: 'Đã hủy',
}

function statusVariant(
  status: string,
): 'success' | 'warning' | 'destructive' | 'neutral' {
  switch (status) {
    case 'paid':
      return 'success'
    case 'pending':
      return 'warning'
    case 'failed':
    case 'cancelled':
      return 'destructive'
    default:
      return 'neutral'
  }
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

function formatPrice(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return `${amount.toLocaleString('vi-VN')} ${currency}`
  }
}

export function CompanyPaymentHistoryTable({
  orders,
  isLoading = false,
  error = null,
  onRetry,
}: CompanyPaymentHistoryTableProps) {
  return (
    <Card className="border-border/70">
      <CardHeader>
        <CardTitle className="font-display text-lg font-semibold">
          Lịch sử thanh toán
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <ErrorBanner message={error} onRetry={onRetry} />
        ) : isLoading ? (
          <div className="space-y-3" data-testid="company-payment-loading">
            {[1, 2, 3].map((item) => (
              <Skeleton key={item} className="h-10 w-full" />
            ))}
          </div>
        ) : orders.length === 0 ? (
          <EmptyState
            title="Chưa có giao dịch"
            description="Các giao dịch của công ty sẽ hiển thị tại đây."
          />
        ) : (
          <div className="-mx-6 overflow-x-auto px-6">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <th className="pb-3 pr-4 font-semibold">Thời gian</th>
                  <th className="pb-3 pr-4 font-semibold">Mã đơn</th>
                  <th className="pb-3 pr-4 text-right font-semibold">Số tiền</th>
                  <th className="pb-3 font-semibold">Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr
                    key={order.id}
                    className="border-b border-border/60 last:border-0"
                  >
                    <td className="whitespace-nowrap py-3 pr-4 text-muted-foreground">
                      {formatDateTime(order.created_at)}
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-foreground">
                      {order.internal_order_id}
                    </td>
                    <td className="py-3 pr-4 text-right font-medium text-foreground">
                      {formatPrice(order.amount, order.currency)}
                    </td>
                    <td className="py-3">
                      <Badge variant={statusVariant(order.status)}>
                        {STATUS_LABELS[order.status] ?? order.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
