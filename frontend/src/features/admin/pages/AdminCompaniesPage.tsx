import { useCallback, useEffect, useState } from 'react'
import { Building, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { getAdminCompanies } from '@/api/admin'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { CompanyDeactivateModal } from '@/features/admin/components/CompanyDeactivateModal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { COMPANY_SIZE_LABELS } from '@/types/company'
import type { AdminCompany, AdminCompanyList } from '@/types/admin'

export const ADMIN_COMPANY_PAGE_SIZE = 10

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; data: AdminCompanyList }

function formatCreatedAt(dateString: string): string {
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleDateString('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function AdminCompaniesPage() {
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selected, setSelected] = useState<AdminCompany | null>(null)

  const load = useCallback(async () => {
    setListState({ kind: 'loading' })
    try {
      const data = await getAdminCompanies({
        skip: (page - 1) * ADMIN_COMPANY_PAGE_SIZE,
        limit: ADMIN_COMPANY_PAGE_SIZE,
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

  const handleLocked = () => {
    setSelected(null)
    void load()
  }

  const totalPages = Math.max(
    1,
    Math.ceil(
      (listState.kind === 'success' ? listState.data.total : 0) /
        ADMIN_COMPANY_PAGE_SIZE,
    ),
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Quản lý công ty"
        description="Xem danh sách công ty trên nền tảng, tìm kiếm và khóa công ty khi cần kiểm duyệt."
      />

      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        aria-label="Tìm kiếm công ty"
      >
        <div className="w-full sm:max-w-xs">
          <Input
            id="admin-company-search"
            name="search"
            type="search"
            placeholder="Tìm theo tên, slug hoặc mã số thuế..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Tìm theo tên, slug hoặc mã số thuế"
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
          {listState.data.items.length === 0 ? (
            <EmptyState
              icon={<Building className="h-6 w-6" aria-hidden="true" />}
              title="Không tìm thấy công ty"
              description={
                searchQuery
                  ? 'Không có công ty nào khớp với từ khóa hiện tại. Hãy điều chỉnh tìm kiếm để xem thêm kết quả.'
                  : 'Chưa có công ty nào trên nền tảng.'
              }
            />
          ) : (
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th scope="col" className="px-4 py-3 font-medium">
                        Công ty
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Slug
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Mã số thuế
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Quy mô
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Ngày tạo
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Trạng thái
                      </th>
                      <th scope="col" className="px-4 py-3 text-right font-medium">
                        Hành động
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {listState.data.items.map((company) => (
                      <tr
                        key={company.id}
                        className="border-b last:border-b-0 hover:bg-muted/40"
                      >
                        <td className="px-4 py-3">
                          <span className="flex items-center gap-2">
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                              {company.name.charAt(0).toUpperCase()}
                            </span>
                            <span className="truncate font-medium">
                              {company.name}
                            </span>
                          </span>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {company.slug}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {company.tax_code}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="neutral">
                            {COMPANY_SIZE_LABELS[company.size]}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatCreatedAt(company.created_at) || 'Không rõ'}
                        </td>
                        <td className="px-4 py-3">
                          {company.is_deleted ? (
                            <Badge variant="destructive">Đã khóa</Badge>
                          ) : (
                            <Badge variant="success">Đang hoạt động</Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={company.is_deleted}
                            onClick={() => setSelected(company)}
                            aria-label={`Khóa công ty ${company.name}`}
                          >
                            Khóa công ty
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

      {selected ? (
        <CompanyDeactivateModal
          company={selected}
          onClose={() => setSelected(null)}
          onSuccess={handleLocked}
        />
      ) : null}
    </div>
  )
}