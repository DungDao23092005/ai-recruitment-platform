import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Eye,
  Search,
  ShieldOff,
  Sparkles,
} from 'lucide-react'
import { getAdminSubscriptions } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import {
  ADMIN_SUBSCRIPTION_CHANGED_DOM_EVENT,
  STREAM_CONNECTED_DOM_EVENT,
} from '@/hooks/useNotificationStream'
import type {
  AdminSubscriptionListItem,
  AdminSubscriptionStatus,
} from '@/types/admin'

export const ADMIN_SUBSCRIPTION_PAGE_SIZE = 10
export const ADMIN_SUBSCRIPTION_REFRESH_DEBOUNCE_MS = 300

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; items: AdminSubscriptionListItem[]; total: number }

const STATUS_META: Record<
  AdminSubscriptionStatus,
  { label: string; variant: 'success' | 'warning' | 'destructive' | 'neutral' }
> = {
  active: { label: 'Đang hoạt động', variant: 'success' },
  pending: { label: 'Chờ kích hoạt', variant: 'warning' },
  expired: { label: 'Hết hạn', variant: 'neutral' },
  cancelled: { label: 'Đã hủy', variant: 'destructive' },
}

const STATUS_FILTERS: { value: '' | AdminSubscriptionStatus; label: string }[] = [
  { value: '', label: 'Tất cả trạng thái' },
  { value: 'active', label: 'Đang hoạt động' },
  { value: 'pending', label: 'Chờ kích hoạt' },
  { value: 'expired', label: 'Hết hạn' },
  { value: 'cancelled', label: 'Đã hủy' },
]

export function formatSubscriptionDate(value: string | null): string {
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

export function SubscriptionStatusBadge({
  status,
}: {
  status: AdminSubscriptionStatus
}) {
  const meta = STATUS_META[status] ?? {
    label: status,
    variant: 'neutral' as const,
  }
  return <Badge variant={meta.variant}>{meta.label}</Badge>
}

interface AdminSubscriptionListProps {
  onChangePlan: (subscription: AdminSubscriptionListItem) => void
  onRevoke: (subscription: AdminSubscriptionListItem) => void
  onViewDetail: (subscription: AdminSubscriptionListItem) => void
  /**
   * Monotonic counter bumped by the parent after a local mutation so the list
   * silently refetches without unmounting (keeping page/search/filter state).
   */
  refreshSignal?: number
}

export function AdminSubscriptionList({
  onChangePlan,
  onRevoke,
  onViewDetail,
  refreshSignal = 0,
}: AdminSubscriptionListProps) {
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<
    '' | AdminSubscriptionStatus
  >('')

  // Latest query params, read by the silent-refresh path so event-driven
  // refetches use the current page/search/filter without re-binding listeners.
  const paramsRef = useRef({ page, searchQuery, statusFilter })
  paramsRef.current = { page, searchQuery, statusFilter }

  // Monotonic request generation: only the newest in-flight request may write
  // state, so a slow earlier response can never clobber a newer one.
  const loadGenerationRef = useRef(0)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchList = useCallback(async (mode: 'initial' | 'silent') => {
    const generation = ++loadGenerationRef.current
    const {
      page: currentPage,
      searchQuery: currentSearch,
      statusFilter: currentStatus,
    } = paramsRef.current

    if (mode === 'initial') {
      setListState({ kind: 'loading' })
    }

    try {
      const data = await getAdminSubscriptions({
        skip: (currentPage - 1) * ADMIN_SUBSCRIPTION_PAGE_SIZE,
        limit: ADMIN_SUBSCRIPTION_PAGE_SIZE,
        search: currentSearch.trim() || undefined,
        status_filter: currentStatus || undefined,
      })
      if (generation !== loadGenerationRef.current) return
      setListState({ kind: 'success', items: data.items, total: data.total })
    } catch (err) {
      if (generation !== loadGenerationRef.current) return
      if (mode === 'initial') {
        setListState({ kind: 'error', message: getFriendlyErrorMessage(err) })
      } else {
        // A silent refresh must never clear the table or surface a fake error.
        console.warn('Silent subscription refresh failed:', err)
      }
    }
  }, [])

  useEffect(() => {
    void fetchList('initial')
  }, [page, searchQuery, statusFilter, fetchList])

  const scheduleSilentRefresh = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null
      void fetchList('silent')
    }, ADMIN_SUBSCRIPTION_REFRESH_DEBOUNCE_MS)
  }, [fetchList])

  // Realtime + lifecycle refresh: coalesce bursts of change events, catch up on
  // (re)connect, and refetch when the tab becomes visible again.
  useEffect(() => {
    const handleChanged = () => scheduleSilentRefresh()
    const handleConnected = () => scheduleSilentRefresh()
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') scheduleSilentRefresh()
    }

    window.addEventListener(ADMIN_SUBSCRIPTION_CHANGED_DOM_EVENT, handleChanged)
    window.addEventListener(STREAM_CONNECTED_DOM_EVENT, handleConnected)
    document.addEventListener('visibilitychange', handleVisibility)

    return () => {
      window.removeEventListener(ADMIN_SUBSCRIPTION_CHANGED_DOM_EVENT, handleChanged)
      window.removeEventListener(STREAM_CONNECTED_DOM_EVENT, handleConnected)
      document.removeEventListener('visibilitychange', handleVisibility)
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
    }
  }, [scheduleSilentRefresh])

  // Local mutation refresh without remounting (preserves page/search/filter).
  const didMountRef = useRef(false)
  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true
      return
    }
    void fetchList('silent')
  }, [refreshSignal, fetchList])

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    setPage(1)
    setSearchQuery(search.trim())
  }

  const handleStatusChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setPage(1)
    setStatusFilter(event.target.value as '' | AdminSubscriptionStatus)
  }

  const items = listState.kind === 'success' ? listState.items : []
  const total = listState.kind === 'success' ? listState.total : 0
  const totalPages = Math.max(1, Math.ceil(total / ADMIN_SUBSCRIPTION_PAGE_SIZE))

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        aria-label="Tìm kiếm thuê bao người dùng"
      >
        <div className="w-full sm:max-w-xs">
          <Input
            id="admin-subscription-search"
            name="search"
            type="search"
            placeholder="Tìm theo email người dùng..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Tìm theo email người dùng"
          />
        </div>
        <div className="w-full sm:max-w-xs">
          <label htmlFor="admin-subscription-status" className="sr-only">
            Lọc theo trạng thái
          </label>
          <select
            id="admin-subscription-status"
            name="status_filter"
            value={statusFilter}
            onChange={handleStatusChange}
            aria-label="Lọc theo trạng thái"
            className="flex h-9 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {STATUS_FILTERS.map((option) => (
              <option key={option.value || 'all'} value={option.value}>
                {option.label}
              </option>
            ))}
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
        <ErrorBanner message={listState.message} onRetry={() => void fetchList('initial')} />
      ) : null}

      {listState.kind === 'success' ? (
        <>
          {items.length === 0 ? (
            <EmptyState
              icon={<CreditCard className="h-6 w-6" aria-hidden="true" />}
              title="Không tìm thấy thuê bao"
              description={
                searchQuery || statusFilter
                  ? 'Không có thuê bao nào khớp với bộ lọc hiện tại.'
                  : 'Chưa có thuê bao nào trên nền tảng.'
              }
            />
          ) : (
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[960px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th scope="col" className="px-4 py-3 font-medium">Người dùng</th>
                      <th scope="col" className="px-4 py-3 font-medium">Gói</th>
                      <th scope="col" className="px-4 py-3 font-medium">Trạng thái</th>
                      <th scope="col" className="px-4 py-3 font-medium">Hết hạn</th>
                      <th scope="col" className="px-4 py-3 font-medium">Hạn mức đã dùng</th>
                      <th scope="col" className="px-4 py-3 text-right font-medium">Hành động</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => {
                      const actionBlocked =
                        item.has_multiple_active || item.has_unresolved_payment
                      const changePlanDisabled =
                        item.effective_status !== 'active' || actionBlocked
                      const revokeDisabled =
                        (item.effective_status !== 'active' &&
                          item.effective_status !== 'pending') ||
                        actionBlocked
                      const blockedTitle = actionBlocked
                        ? 'Không thể thao tác khi người dùng có nhiều gói hoạt động hoặc giao dịch chưa xử lý.'
                        : undefined
                      return (
                      <tr
                        key={item.id}
                        className="border-b last:border-b-0 hover:bg-muted/40"
                      >
                        <td className="px-4 py-3">
                          <span className="font-medium">
                            {item.user_email ?? item.user_id}
                          </span>
                          {item.total_subscriptions > 1 ||
                          item.has_multiple_active ||
                          item.has_unresolved_payment ? (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {item.total_subscriptions > 1 ? (
                                <Badge
                                  variant="neutral"
                                  title={`Người dùng có ${item.total_subscriptions} thuê bao trong lịch sử`}
                                >
                                  {item.total_subscriptions} thuê bao
                                </Badge>
                              ) : null}
                              {item.has_multiple_active ? (
                                <Badge
                                  variant="warning"
                                  title="Người dùng có nhiều hơn một gói đang hoạt động"
                                >
                                  Nhiều gói hoạt động
                                </Badge>
                              ) : null}
                              {item.is_entitlement_incident ? (
                                <Badge
                                  variant="destructive"
                                  title={`Có giao dịch đã thanh toán nhưng gói chưa được kích hoạt${
                                    item.incident_internal_order_id
                                      ? ` (${item.incident_internal_order_id})`
                                      : ''
                                  }`}
                                >
                                  Sự cố quyền lợi
                                </Badge>
                              ) : null}
                              {item.has_unresolved_payment &&
                              !item.is_entitlement_incident ? (
                                <Badge
                                  variant="warning"
                                  title="Đang có giao dịch VNPAY chờ xử lý"
                                >
                                  Thanh toán treo
                                </Badge>
                              ) : null}
                            </div>
                          ) : null}
                        </td>
                        <td className="px-4 py-3">
                          {item.plan_name ?? '—'}
                        </td>
                        <td className="px-4 py-3">
                          <SubscriptionStatusBadge status={item.effective_status} />
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatSubscriptionDate(item.expires_at)}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          <div>
                            Tin: {item.job_posts_used}/{item.max_job_posts}
                          </div>
                          <div>
                            Tìm: {item.candidate_searches_used}/
                            {item.max_candidate_searches}
                          </div>
                          <div>
                            AI: {item.ai_features_used}/{item.max_ai_features}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            aria-label={`Xem chi tiết thuê bao ${item.user_email ?? item.id}`}
                            onClick={() => onViewDetail(item)}
                          >
                            <Eye className="h-4 w-4 mr-1" aria-hidden="true" />
                            Chi tiết
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="ml-1"
                            aria-label={`Đổi gói cho ${item.user_email ?? item.id}`}
                            disabled={changePlanDisabled}
                            title={blockedTitle}
                            onClick={() => onChangePlan(item)}
                          >
                            <Sparkles className="h-4 w-4 mr-1" aria-hidden="true" />
                            Đổi gói
                          </Button>
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            className="ml-1"
                            aria-label={`Thu hồi gói của ${item.user_email ?? item.id}`}
                            disabled={revokeDisabled}
                            title={blockedTitle}
                            onClick={() => onRevoke(item)}
                          >
                            <ShieldOff className="h-4 w-4 mr-1" aria-hidden="true" />
                            Thu hồi
                          </Button>
                        </td>
                      </tr>
                      )
                    })}
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
