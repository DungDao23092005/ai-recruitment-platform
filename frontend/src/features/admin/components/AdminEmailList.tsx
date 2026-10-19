import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Mail,
  RefreshCw,
  Search,
} from 'lucide-react'
import { getAdminEmails, getAdminEmailStats, retryAdminEmail } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type {
  AdminEmailOutboxMessage,
  AdminEmailOutboxStats,
  AdminEmailStatus,
} from '@/types/admin'

export const ADMIN_EMAIL_PAGE_SIZE = 10

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; items: AdminEmailOutboxMessage[]; total: number }

type StatsState =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'success'; stats: AdminEmailOutboxStats }

const STATUS_META: Record<
  AdminEmailStatus,
  { label: string; variant: 'success' | 'warning' | 'destructive' | 'info' }
> = {
  pending: { label: 'Chờ gửi', variant: 'warning' },
  processing: { label: 'Đang gửi', variant: 'info' },
  sent: { label: 'Đã gửi', variant: 'success' },
  failed: { label: 'Thất bại', variant: 'destructive' },
}

const STATUS_FILTERS: { value: '' | AdminEmailStatus; label: string }[] = [
  { value: '', label: 'Tất cả trạng thái' },
  { value: 'pending', label: 'Chờ gửi' },
  { value: 'processing', label: 'Đang gửi' },
  { value: 'sent', label: 'Đã gửi' },
  { value: 'failed', label: 'Thất bại' },
]

export function formatEmailDateTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Ho_Chi_Minh',
  })
}

export function EmailStatusBadge({ status }: { status: AdminEmailStatus }) {
  const meta = STATUS_META[status] ?? {
    label: status,
    variant: 'neutral' as const,
  }
  return <Badge variant={meta.variant}>{meta.label}</Badge>
}

function StatsRow({ state }: { state: StatsState }) {
  const entries: { key: keyof AdminEmailOutboxStats; label: string }[] = [
    { key: 'pending', label: 'Chờ gửi' },
    { key: 'processing', label: 'Đang gửi' },
    { key: 'sent', label: 'Đã gửi' },
    { key: 'failed', label: 'Thất bại' },
    { key: 'total', label: 'Tổng' },
  ]

  if (state.kind === 'loading') {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {Array.from({ length: 5 }).map((_, index) => (
          <Skeleton key={index} className="h-20 w-full" />
        ))}
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <ErrorBanner message="Không thể tải số liệu hàng đợi email." />
    )
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {entries.map((entry) => (
        <Card key={entry.key}>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {entry.label}
            </p>
            <p className="mt-1 font-display text-2xl font-bold text-foreground">
              {state.stats[entry.key]}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export function AdminEmailList() {
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [statsState, setStatsState] = useState<StatsState>({ kind: 'loading' })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'' | AdminEmailStatus>('')
  const [retryError, setRetryError] = useState<string | null>(null)
  const [retryingId, setRetryingId] = useState<string | null>(null)

  const paramsRef = useRef({ page, searchQuery, statusFilter })
  paramsRef.current = { page, searchQuery, statusFilter }

  const loadGenerationRef = useRef(0)

  const fetchStats = useCallback(async () => {
    try {
      const stats = await getAdminEmailStats()
      setStatsState({ kind: 'success', stats })
    } catch {
      setStatsState({ kind: 'error' })
    }
  }, [])

  const fetchList = useCallback(async () => {
    const generation = ++loadGenerationRef.current
    const {
      page: currentPage,
      searchQuery: currentSearch,
      statusFilter: currentStatus,
    } = paramsRef.current

    setListState({ kind: 'loading' })

    try {
      const data = await getAdminEmails({
        skip: (currentPage - 1) * ADMIN_EMAIL_PAGE_SIZE,
        limit: ADMIN_EMAIL_PAGE_SIZE,
        search: currentSearch.trim() || undefined,
        status: currentStatus || undefined,
      })
      if (generation !== loadGenerationRef.current) return
      setListState({ kind: 'success', items: data.items, total: data.total })
    } catch (err) {
      if (generation !== loadGenerationRef.current) return
      setListState({ kind: 'error', message: getFriendlyErrorMessage(err) })
    }
  }, [])

  useEffect(() => {
    void fetchStats()
  }, [fetchStats])

  useEffect(() => {
    void fetchList()
  }, [page, searchQuery, statusFilter, fetchList])

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    setPage(1)
    setSearchQuery(search.trim())
  }

  const handleStatusChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setPage(1)
    setStatusFilter(event.target.value as '' | AdminEmailStatus)
  }

  const handleRetry = async (message: AdminEmailOutboxMessage) => {
    setRetryError(null)
    setRetryingId(message.id)
    try {
      await retryAdminEmail(message.id)
      await Promise.all([fetchList(), fetchStats()])
    } catch (err) {
      setRetryError(getFriendlyErrorMessage(err))
    } finally {
      setRetryingId(null)
    }
  }

  const items = listState.kind === 'success' ? listState.items : []
  const total = listState.kind === 'success' ? listState.total : 0
  const totalPages = Math.max(1, Math.ceil(total / ADMIN_EMAIL_PAGE_SIZE))

  return (
    <div className="space-y-6">
      <StatsRow state={statsState} />

      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        aria-label="Tìm kiếm email hàng đợi"
      >
        <div className="w-full sm:max-w-xs">
          <Input
            id="admin-email-search"
            name="search"
            type="search"
            placeholder="Tìm theo email hoặc tiêu đề..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Tìm theo email hoặc tiêu đề"
          />
        </div>
        <div className="w-full sm:max-w-xs">
          <label htmlFor="admin-email-status" className="sr-only">
            Lọc theo trạng thái
          </label>
          <select
            id="admin-email-status"
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

      {retryError ? <ErrorBanner message={retryError} /> : null}

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
        <ErrorBanner
          message={listState.message}
          onRetry={() => void fetchList()}
        />
      ) : null}

      {listState.kind === 'success' ? (
        <>
          {items.length === 0 ? (
            <EmptyState
              icon={<Mail className="h-6 w-6" aria-hidden="true" />}
              title="Không tìm thấy email"
              description={
                searchQuery || statusFilter
                  ? 'Không có email nào khớp với bộ lọc hiện tại.'
                  : 'Hàng đợi email đang trống.'
              }
            />
          ) : (
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[900px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th scope="col" className="px-4 py-3 font-medium">Người nhận</th>
                      <th scope="col" className="px-4 py-3 font-medium">Sự kiện</th>
                      <th scope="col" className="px-4 py-3 font-medium">Trạng thái</th>
                      <th scope="col" className="px-4 py-3 font-medium">Số lần thử</th>
                      <th scope="col" className="px-4 py-3 font-medium">Thời gian</th>
                      <th scope="col" className="px-4 py-3 text-right font-medium">Hành động</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr
                        key={item.id}
                        className="border-b last:border-b-0 hover:bg-muted/40"
                      >
                        <td className="px-4 py-3">
                          <span className="font-medium">{item.to_email}</span>
                          <p className="mt-0.5 max-w-[280px] truncate text-xs text-muted-foreground">
                            {item.subject}
                          </p>
                          {item.status === 'failed' && item.last_error ? (
                            <p className="mt-0.5 max-w-[280px] truncate text-xs text-destructive">
                              {item.last_error}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="neutral">{item.event_type}</Badge>
                        </td>
                        <td className="px-4 py-3">
                          <EmailStatusBadge status={item.status} />
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          {item.attempts}/{item.max_attempts}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          {item.status === 'sent'
                            ? formatEmailDateTime(item.sent_at)
                            : formatEmailDateTime(item.next_attempt_at)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            aria-label={`Gửi lại email ${item.id}`}
                            disabled={item.status === 'processing' || retryingId === item.id}
                            onClick={() => void handleRetry(item)}
                          >
                            <RefreshCw className="mr-1 h-4 w-4" aria-hidden="true" />
                            Gửi lại
                          </Button>
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
