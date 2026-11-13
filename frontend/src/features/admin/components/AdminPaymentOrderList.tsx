import { useCallback, useEffect, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  ReceiptText,
  Search,
} from 'lucide-react'
import { getAdminPaymentOrders } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type {
  AdminPaymentOrder,
  AdminPaymentOrderStatus,
  AdminPaymentProvider,
  AdminSubscriptionScope,
} from '@/types/admin'

export const ADMIN_PAYMENT_ORDER_PAGE_SIZE = 10

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; items: AdminPaymentOrder[]; total: number }

const STATUS_META: Record<
  AdminPaymentOrderStatus,
  { label: string; variant: 'success' | 'warning' | 'destructive' | 'neutral' }
> = {
  pending: { label: 'Chờ thanh toán', variant: 'warning' },
  paid: { label: 'Đã thanh toán', variant: 'success' },
  failed: { label: 'Thất bại', variant: 'destructive' },
  cancelled: { label: 'Đã hủy', variant: 'neutral' },
  expired: { label: 'Hết hạn', variant: 'neutral' },
}

const PROVIDER_LABELS: Record<AdminPaymentProvider, string> = {
  vnpay: 'VNPAY',
  momo: 'MoMo',
}

const SCOPE_LABELS: Record<AdminSubscriptionScope, string> = {
  company_recruiting: 'Doanh nghiệp',
  candidate_personal: 'Ứng viên',
  legacy_recruiter_personal: 'Nhà tuyển dụng (legacy)',
}

function formatAmount(amount: number, currency: string): string {
  const value = new Intl.NumberFormat('vi-VN').format(amount)
  return currency === 'VND' ? `${value} ₫` : `${value} ${currency}`
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Asia/Ho_Chi_Minh',
  })
}

export function PaymentOrderStatusBadge({
  status,
}: {
  status: AdminPaymentOrderStatus
}) {
  const meta = STATUS_META[status] ?? {
    label: status,
    variant: 'neutral' as const,
  }
  return <Badge variant={meta.variant}>{meta.label}</Badge>
}

export function AdminPaymentOrderList() {
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<
    '' | AdminPaymentOrderStatus
  >('')
  const [scopeFilter, setScopeFilter] = useState<
    '' | AdminSubscriptionScope
  >('')

  const load = useCallback(async () => {
    setListState({ kind: 'loading' })
    try {
      const data = await getAdminPaymentOrders({
        skip: (page - 1) * ADMIN_PAYMENT_ORDER_PAGE_SIZE,
        limit: ADMIN_PAYMENT_ORDER_PAGE_SIZE,
        search: searchQuery.trim() || undefined,
        status: statusFilter || undefined,
        scope: scopeFilter || undefined,
      })
      const lastPage = Math.max(
        1,
        Math.ceil(data.total / ADMIN_PAYMENT_ORDER_PAGE_SIZE),
      )
      if (page > lastPage) {
        setPage(lastPage)
        return
      }
      setListState({ kind: 'success', items: data.items, total: data.total })
    } catch (err) {
      setListState({ kind: 'error', message: getFriendlyErrorMessage(err) })
    }
  }, [page, searchQuery, statusFilter, scopeFilter])

  useEffect(() => {
    void load()
  }, [load])

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    setPage(1)
    setSearchQuery(search.trim())
  }

  const items = listState.kind === 'success' ? listState.items : []
  const total = listState.kind === 'success' ? listState.total : 0
  const totalPages = Math.max(
    1,
    Math.ceil(total / ADMIN_PAYMENT_ORDER_PAGE_SIZE),
  )

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col gap-3 lg:flex-row lg:items-end"
        aria-label="Tìm kiếm đơn thanh toán"
      >
        <div className="w-full lg:max-w-xs">
          <Input
            id="admin-payment-order-search"
            name="search"
            type="search"
            placeholder="Tìm theo mã đơn hoặc email..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Tìm theo mã đơn hoặc email"
          />
        </div>
        <div className="w-full lg:max-w-[12rem]">
          <label htmlFor="admin-payment-order-status" className="sr-only">
            Lọc theo trạng thái
          </label>
          <select
            id="admin-payment-order-status"
            name="status"
            value={statusFilter}
            onChange={(event) => {
              setPage(1)
              setStatusFilter(event.target.value as '' | AdminPaymentOrderStatus)
            }}
            aria-label="Lọc theo trạng thái"
            className="flex h-9 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">Tất cả trạng thái</option>
            <option value="pending">Chờ thanh toán</option>
            <option value="paid">Đã thanh toán</option>
            <option value="failed">Thất bại</option>
            <option value="cancelled">Đã hủy</option>
            <option value="expired">Hết hạn</option>
          </select>
        </div>
        <div className="w-full lg:max-w-[12rem]">
          <label htmlFor="admin-payment-order-scope" className="sr-only">
            Lọc theo phạm vi
          </label>
          <select
            id="admin-payment-order-scope"
            name="scope"
            value={scopeFilter}
            onChange={(event) => {
              setPage(1)
              setScopeFilter(event.target.value as '' | AdminSubscriptionScope)
            }}
            aria-label="Lọc theo phạm vi"
            className="flex h-9 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">Tất cả phạm vi</option>
            <option value="company_recruiting">Doanh nghiệp</option>
            <option value="candidate_personal">Ứng viên</option>
            <option value="legacy_recruiter_personal">
              Nhà tuyển dụng (legacy)
            </option>
          </select>
        </div>
        <Button type="submit">
          <Search className="h-4 w-4" aria-hidden="true" />
          Tìm kiếm
        </Button>
      </form>

      {listState.kind === 'loading' ? (
        <Card>
          <CardContent className="space-y-3 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-10 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {listState.kind === 'error' ? (
        <ErrorBanner message={listState.message} onRetry={load} />
      ) : null}

      {listState.kind === 'success' ? (
        <>
          {items.length === 0 ? (
            <EmptyState
              icon={<ReceiptText className="h-6 w-6" aria-hidden="true" />}
              title="Không tìm thấy đơn thanh toán"
              description={
                searchQuery || statusFilter || scopeFilter
                  ? 'Không có đơn thanh toán nào khớp với bộ lọc hiện tại.'
                  : 'Chưa có đơn thanh toán nào trên nền tảng.'
              }
            />
          ) : (
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[980px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th scope="col" className="px-4 py-3 font-medium">
                        Mã đơn hàng
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Người mua
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Gói dịch vụ
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Phạm vi
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Số tiền
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Cổng thanh toán
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Trạng thái
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Ngày tạo
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Ngày thanh toán
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((order) => (
                      <tr
                        key={order.id}
                        className="border-b last:border-b-0 hover:bg-muted/40"
                      >
                        <td className="px-4 py-3 font-mono text-xs">
                          {order.internal_order_id}
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium">
                            {order.user_full_name ||
                              order.user_email ||
                              order.user_id}
                          </div>
                          {order.user_full_name && order.user_email ? (
                            <div className="text-xs text-muted-foreground">
                              {order.user_email}
                            </div>
                          ) : null}
                          {order.company_name ? (
                            <div className="text-xs text-muted-foreground">
                              {order.company_name}
                            </div>
                          ) : null}
                        </td>
                        <td className="px-4 py-3">
                          <div>{order.plan_name ?? '—'}</div>
                          <Badge
                            variant="info"
                            className="mt-1"
                          >
                            {order.plan_audience === 'candidate'
                              ? 'Ứng viên'
                              : 'Doanh nghiệp'}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {SCOPE_LABELS[order.scope] ?? order.scope}
                        </td>
                        <td className="px-4 py-3 font-medium">
                          {formatAmount(order.amount, order.currency)}
                        </td>
                        <td className="px-4 py-3">
                          {PROVIDER_LABELS[order.provider] ?? order.provider}
                        </td>
                        <td className="px-4 py-3">
                          <PaymentOrderStatusBadge status={order.status} />
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatDate(order.created_at)}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatDate(order.paid_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

          {totalPages > 1 ? (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                aria-label="Trang trước"
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Trước
              </Button>
              <span className="px-2 text-sm text-muted-foreground">
                Trang {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
                aria-label="Trang sau"
              >
                Sau
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
