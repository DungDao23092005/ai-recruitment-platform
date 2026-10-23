import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  ScrollText,
  Search,
} from 'lucide-react'
import { getAdminAuditLogs } from '@/api/admin'
import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { AdminAuditDetailModal } from '@/features/admin/components/AdminAuditDetailModal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type {
  AdminAuditAction,
  AdminAuditLog,
  AdminAuditLogList,
} from '@/types/admin'

export const ADMIN_AUDIT_PAGE_SIZE = 20

const EMPTY_FILTERS: Filters = {
  search: '',
  action: '',
  createdFrom: '',
  createdTo: '',
}

type AuditBadgeVariant = 'warning' | 'success' | 'destructive'

const ACTION_META: Record<
  AdminAuditAction,
  { label: string; variant: AuditBadgeVariant }
> = {
  user_lock: { label: 'Khóa tài khoản', variant: 'warning' },
  user_unlock: { label: 'Mở khóa tài khoản', variant: 'success' },
  user_delete: { label: 'Xóa tài khoản', variant: 'destructive' },
}

interface Filters {
  search: string
  action: '' | AdminAuditAction
  createdFrom: string
  createdTo: string
}

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; data: AdminAuditLogList }

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Không rõ'
  }
  return date.toLocaleString('vi-VN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function shortId(value: string): string {
  return value.slice(0, 8)
}

function startOfDayIso(value: string): string | undefined {
  if (!value) {
    return undefined
  }
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

function endOfDayIso(value: string): string | undefined {
  if (!value) {
    return undefined
  }
  const date = new Date(`${value}T23:59:59.999`)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

export function AdminAuditPage() {
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [page, setPage] = useState(1)
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS)
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [filterError, setFilterError] = useState<string | null>(null)
  const [selected, setSelected] = useState<AdminAuditLog | null>(null)
  const requestId = useRef(0)

  const load = useCallback(async () => {
    const currentRequest = ++requestId.current
    setListState({ kind: 'loading' })
    try {
      const data = await getAdminAuditLogs({
        skip: (page - 1) * ADMIN_AUDIT_PAGE_SIZE,
        limit: ADMIN_AUDIT_PAGE_SIZE,
        search: filters.search || undefined,
        action: filters.action || undefined,
        created_from: startOfDayIso(filters.createdFrom),
        created_to: endOfDayIso(filters.createdTo),
      })
      if (currentRequest === requestId.current) {
        setListState({ kind: 'success', data })
      }
    } catch (error) {
      if (currentRequest === requestId.current) {
        setListState({
          kind: 'error',
          message: getFriendlyErrorMessage(error),
        })
      }
    }
  }, [filters, page])

  useEffect(() => {
    void load()
  }, [load])

  const hasActiveFilters =
    filters.search.length > 0 ||
    filters.action.length > 0 ||
    filters.createdFrom.length > 0 ||
    filters.createdTo.length > 0
  const hasPendingFilters =
    draft.search.length > 0 ||
    draft.action.length > 0 ||
    draft.createdFrom.length > 0 ||
    draft.createdTo.length > 0

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (
      draft.createdFrom &&
      draft.createdTo &&
      draft.createdFrom > draft.createdTo
    ) {
      setFilterError('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')
      return
    }
    setFilterError(null)
    setFilters({
      search: draft.search.trim(),
      action: draft.action,
      createdFrom: draft.createdFrom,
      createdTo: draft.createdTo,
    })
    setPage(1)
  }

  const handleClear = () => {
    setDraft(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
    setFilterError(null)
    setPage(1)
  }

  const total = listState.kind === 'success' ? listState.data.total : 0
  const totalPages = Math.max(
    1,
    Math.ceil(total / ADMIN_AUDIT_PAGE_SIZE),
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Nhật ký quản trị"
        description="Tra cứu các thao tác khóa, mở khóa và xóa tài khoản do quản trị viên thực hiện. Bản ghi chỉ đọc và luôn được sắp xếp mới nhất trước."
        actions={
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void load()}
            disabled={listState.kind === 'loading'}
          >
            <RefreshCw
              className={listState.kind === 'loading' ? 'animate-spin' : undefined}
              aria-hidden="true"
            />
            Làm mới
          </Button>
        }
      />

      <Card>
        <CardContent className="p-4">
          <form
            onSubmit={handleSubmit}
            aria-label="Bộ lọc nhật ký quản trị"
            className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(0,1.6fr)_12rem_10rem_10rem_auto]"
          >
            <Input
              id="admin-audit-search"
              name="search"
              type="search"
              label="Tìm kiếm"
              placeholder="Lý do, email quản trị viên hoặc người dùng..."
              maxLength={100}
              value={draft.search}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  search: event.target.value,
                }))
              }
            />
            <Select
              id="admin-audit-action"
              name="action"
              label="Hành động"
              value={draft.action}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  action: event.target.value as '' | AdminAuditAction,
                }))
              }
            >
              <option value="">Tất cả hành động</option>
              <option value="user_lock">Khóa tài khoản</option>
              <option value="user_unlock">Mở khóa tài khoản</option>
              <option value="user_delete">Xóa tài khoản</option>
            </Select>
            <Input
              id="admin-audit-from"
              name="created_from"
              type="date"
              label="Từ ngày"
              value={draft.createdFrom}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  createdFrom: event.target.value,
                }))
              }
            />
            <Input
              id="admin-audit-to"
              name="created_to"
              type="date"
              label="Đến ngày"
              value={draft.createdTo}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  createdTo: event.target.value,
                }))
              }
            />
            <div className="flex items-end gap-2">
              <Button type="submit" className="flex-1 xl:flex-none">
                <Search aria-hidden="true" />
                Tra cứu
              </Button>
              {hasActiveFilters || hasPendingFilters ? (
                <Button type="button" variant="ghost" onClick={handleClear}>
                  Xóa lọc
                </Button>
              ) : null}
            </div>
          </form>
          {filterError ? (
            <p
              role="alert"
              className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
            >
              {filterError}
            </p>
          ) : null}
          <p className="mt-3 text-xs text-muted-foreground">
            Khoảng ngày được tính trọn ngày theo múi giờ hiện tại của trình duyệt.
          </p>
        </CardContent>
      </Card>

      {listState.kind === 'loading' ? (
        <Card aria-busy="true">
          <CardContent className="space-y-3 p-4">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-12 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {listState.kind === 'error' ? (
        <ErrorBanner message={listState.message} onRetry={load} />
      ) : null}

      {listState.kind === 'success' ? (
        <>
          <p className="text-sm text-muted-foreground">
            {hasActiveFilters
              ? `${total.toLocaleString('vi-VN')} bản ghi phù hợp`
              : `${total.toLocaleString('vi-VN')} bản ghi`}
          </p>

          {listState.data.items.length === 0 ? (
            <EmptyState
              icon={<ScrollText className="h-6 w-6" aria-hidden="true" />}
              title={
                hasActiveFilters
                  ? 'Không có bản ghi phù hợp'
                  : 'Chưa có bản ghi nào'
              }
              description={
                hasActiveFilters
                  ? 'Thử thay đổi từ khóa, hành động hoặc khoảng thời gian để xem thêm kết quả.'
                  : 'Các thao tác khóa, mở khóa hoặc xóa tài khoản sẽ xuất hiện tại đây.'
              }
            >
              {hasActiveFilters ? (
                <Button type="button" variant="outline" onClick={handleClear}>
                  Xóa bộ lọc
                </Button>
              ) : null}
            </EmptyState>
          ) : (
            <Card className="overflow-hidden">
              <CardContent className="overflow-x-auto p-0">
                <table
                  className="w-full min-w-[980px] text-left text-sm"
                  aria-label="Bảng nhật ký quản trị"
                >
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th scope="col" className="px-4 py-3 font-medium">
                        Thời gian
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Hành động
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Quản trị viên
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Đối tượng
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Lý do
                      </th>
                      <th scope="col" className="px-4 py-3 text-right font-medium">
                        Chi tiết
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {listState.data.items.map((log) => {
                      const meta = ACTION_META[log.action]
                      return (
                        <tr
                          key={log.id}
                          className="border-b last:border-b-0 hover:bg-muted/40"
                        >
                          <td className="px-4 py-3 align-top">
                            <time
                              dateTime={log.created_at}
                              className="block font-medium text-foreground"
                            >
                              {formatTimestamp(log.created_at)}
                            </time>
                            <span className="mt-0.5 block font-mono text-xs text-muted-foreground">
                              #{shortId(log.id)}
                            </span>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <Badge variant={meta.variant}>{meta.label}</Badge>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <span
                              className="block max-w-[220px] truncate"
                              title={log.admin_email ?? log.admin_id}
                            >
                              {log.admin_email ?? 'Không xác định'}
                            </span>
                            <span className="mt-0.5 block font-mono text-xs text-muted-foreground">
                              {shortId(log.admin_id)}
                            </span>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <span
                              className="block max-w-[220px] truncate"
                              title={log.target_user_email ?? log.target_user_id}
                            >
                              {log.target_user_email ?? 'Không xác định'}
                            </span>
                            <span className="mt-0.5 block font-mono text-xs text-muted-foreground">
                              {shortId(log.target_user_id)}
                            </span>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <span
                              className="block max-w-[280px] text-muted-foreground"
                              title={log.reason ?? undefined}
                            >
                              {log.reason ?? 'Không có lý do'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right align-top">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => setSelected(log)}
                              aria-label={`Xem chi tiết bản ghi ${shortId(log.id)}`}
                            >
                              Chi tiết
                              <ChevronRight aria-hidden="true" />
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
            <nav
              aria-label="Phân trang nhật ký quản trị"
              className="flex items-center justify-center gap-2"
            >
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                aria-label="Trang trước"
              >
                <ChevronLeft aria-hidden="true" />
                Trước
              </Button>
              <span className="px-2 text-sm text-muted-foreground">
                Trang {page} / {totalPages}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
                aria-label="Trang sau"
              >
                Sau
                <ChevronRight aria-hidden="true" />
              </Button>
            </nav>
          ) : null}
        </>
      ) : null}

      {selected ? (
        <AdminAuditDetailModal
          log={selected}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </div>
  )
}
