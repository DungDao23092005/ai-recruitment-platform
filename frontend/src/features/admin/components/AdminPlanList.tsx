import { useCallback, useEffect, useState } from 'react'
import { Building, ChevronLeft, ChevronRight, Search, Edit, Lock, Unlock } from 'lucide-react'
import { getAdminPlans } from '@/api/admin'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import type { AdminPlanRead } from '@/types/admin'
import { getFriendlyErrorMessage } from '@/utils/errors'

export const ADMIN_PLAN_PAGE_SIZE = 10

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; data: AdminPlanRead[] }

function formatDuration(days: number): string {
  if (days >= 365) {
    const years = Math.floor(days / 365)
    return `${years} ${years > 1 ? 'năm' : 'năm'}`
  }
  if (days >= 30) {
    const months = Math.floor(days / 30)
    return `${months} ${months > 1 ? 'tháng' : 'tháng'}`
  }
  return `${days} ${days > 1 ? 'ngày' : 'ngày'}`
}

interface AdminPlanListProps {
  onEdit: (plan: AdminPlanRead) => void
  onStatus: (plan: AdminPlanRead) => void
}

export function AdminPlanList({ onEdit, onStatus }: AdminPlanListProps) {
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const load = useCallback(async () => {
    setListState({ kind: 'loading' })
    try {
      const data = await getAdminPlans({
        skip: (page - 1) * ADMIN_PLAN_PAGE_SIZE,
        limit: ADMIN_PLAN_PAGE_SIZE,
        search: searchQuery.trim() || undefined,
      })
      setListState({ kind: 'success', data })
    } catch (err) {
      setListState({ kind: 'error', message: getFriendlyErrorMessage(err) })
    }
  }, [page, searchQuery])

  useEffect(() => {
    void load()
  }, [load])

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    setPage(1)
    setSearchQuery(search.trim())
  }

  const plans = listState.kind === 'success' ? listState.data : []
  const totalPages = Math.max(1, Math.ceil(plans.length / ADMIN_PLAN_PAGE_SIZE))

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Gói tuyển dụng"
        description="Xem danh sách gói tuyển dụng, tìm kiếm và thay đổi trạng thái."
      />

      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        aria-label="Tìm kiếm gói tuyển dụng"
      >
        <div className="w-full sm:max-w-xs">
          <Input
            id="admin-plan-search"
            name="search"
            type="search"
            placeholder="Tìm theo tên gói..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Tìm theo tên gói"
          />
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
          {plans.length === 0 ? (
            <EmptyState
              icon={<Building className="h-6 w-6" aria-hidden="true" />}
              title="Không tìm thấy gói"
              description={
                searchQuery
                  ? 'Không có gói tuyển dụng nào khớp với từ khóa hiện tại. Hãy điều chỉnh tìm kiếm để xem thêm kết quả.'
                  : 'Chưa có gói tuyển dụng nào trên nền tảng.'
              }
            />
          ) : (
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th scope="col" className="px-4 py-3 font-medium">Tên gói</th>
                      <th scope="col" className="px-4 py-3 font-medium">Giá</th>
                      <th scope="col" className="px-4 py-3 font-medium">Thời lượng</th>
                      <th scope="col" className="px-4 py-3 font-medium">Số lượng bài đăng</th>
                      <th scope="col" className="px-4 py-3 font-medium">Tìm kiếm ứng viên</th>
                      <th scope="col" className="px-4 py-3 font-medium">AI features</th>
                      <th scope="col" className="px-4 py-3 font-medium">Thứ tự hiển thị</th>
                      <th scope="col" className="px-4 py-3 font-medium">Trạng thái</th>
                      <th scope="col" className="px-4 py-3 text-right font-medium">Hành động</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plans.map((plan: AdminPlanRead) => (
                      <tr
                        key={plan.id}
                        className="border-b last:border-b-0 hover:bg-muted/40"
                      >
                        <td className="px-4 py-3">
                          <span className="font-medium">{plan.name}</span>
                        </td>
                        <td className="px-4 py-3">
                          {plan.currency} {plan.price.toLocaleString()}
                        </td>
                        <td className="px-4 py-3">
                          {formatDuration(plan.duration_days)}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{plan.max_job_posts}</td>
                        <td className="px-4 py-3 text-muted-foreground">{plan.max_candidate_searches ?? '-'}</td>
                        <td className="px-4 py-3 text-muted-foreground">{plan.max_ai_features ?? '-'}</td>
                        <td className="px-4 py-3 text-muted-foreground">{plan.display_order}</td>
                        <td className="px-4 py-3">
                          {plan.is_active ? (
                            <Badge variant="success">Hoạt động</Badge>
                          ) : (
                            <Badge variant="destructive">Khóa</Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            aria-label="Sửa gói {plan.name}"
                            onClick={() => onEdit(plan)}
                          >
                            <Edit className="h-4 w-4" aria-hidden="true" />
                            Sửa
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            aria-label={plan.is_active ? `Khóa gói ${plan.name}` : `Mở khóa gói ${plan.name}`}
                            onClick={() => onStatus(plan)}
                          >
                            {plan.is_active ? (
                              <>
                                <Lock className="h-4 w-4 mr-1" aria-hidden="true" />
                                Khóa
                              </>
                            ) : (
                              <>
                                <Unlock className="h-4 w-4 mr-1" aria-hidden="true" />
                                Mở khóa
                              </>
                            )}
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