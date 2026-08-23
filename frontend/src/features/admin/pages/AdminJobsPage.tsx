import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Briefcase,
  ChevronLeft,
  ChevronRight,
  Search,
  Edit,
  Trash2,
  ArrowUpDown,
  Users,
} from 'lucide-react'
import { getAdminJobs } from '@/api/admin'
import { updateMyJobStatus, deleteMyJob } from '@/api/jobs'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { getFriendlyErrorMessage } from '@/utils/errors'
import {
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  WORKPLACE_TYPE_LABELS,
  type JobStatus,
} from '@/types/job'
import type { AdminJob, AdminJobList } from '@/types/admin'

export const ADMIN_JOB_PAGE_SIZE = 10

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; data: AdminJobList }

const STATUS_BADGE_VARIANT: Record<
  AdminJob['status'],
  'success' | 'warning' | 'destructive' | 'neutral' | 'ai-gradient' | 'outline-ai' | 'info'
> = {
  draft: 'neutral',
  published: 'success',
  closed: 'destructive',
  expired: 'warning',
}

const TYPE_BADGE_VARIANT: Record<
  AdminJob['job_type'],
  'success' | 'warning' | 'destructive' | 'neutral' | 'ai-gradient' | 'outline-ai' | 'info'
> = {
  full_time: 'neutral',
  part_time: 'info',
  contract: 'warning',
  internship: 'neutral',
}

const ALLOWED_STATUS_TRANSITIONS: Record<JobStatus, JobStatus[]> = {
  draft: ['published'],
  published: ['closed'],
  closed: ['published'],
  expired: [],
}

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

export function AdminJobsPage() {
  const navigate = useNavigate()
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // Delete dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [jobToDelete, setJobToDelete] = useState<AdminJob | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Status change dialog state
  const [statusDialogOpen, setStatusDialogOpen] = useState(false)
  const [jobToStatusChange, setJobToStatusChange] = useState<AdminJob | null>(null)
  const [newStatus, setNewStatus] = useState<JobStatus>('published')
  const [changingStatus, setChangingStatus] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setListState({ kind: 'loading' })
    try {
      const data = await getAdminJobs({
        skip: (page - 1) * ADMIN_JOB_PAGE_SIZE,
        limit: ADMIN_JOB_PAGE_SIZE,
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

  const handleDeleteClick = (job: AdminJob) => {
    setJobToDelete(job)
    setDeleteDialogOpen(true)
  }

  const handleStatusClick = (job: AdminJob) => {
    setJobToStatusChange(job)
    const allowed = ALLOWED_STATUS_TRANSITIONS[job.status] || []
    setNewStatus(allowed[0] || job.status)
    setStatusError(null)
    setStatusDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!jobToDelete) return
    setDeleting(true)
    try {
      await deleteMyJob(jobToDelete.id)
      setDeleteDialogOpen(false)
      setJobToDelete(null)
      await load()
    } catch (err) {
      alert(getFriendlyErrorMessage(err))
    } finally {
      setDeleting(false)
    }
  }

  const handleStatusConfirm = async () => {
    if (!jobToStatusChange) return
    setChangingStatus(true)
    setStatusError(null)
    try {
      await updateMyJobStatus(jobToStatusChange.id, newStatus)
      setStatusDialogOpen(false)
      setJobToStatusChange(null)
      await load()
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err))
    } finally {
      setChangingStatus(false)
    }
  }

  const totalPages = Math.max(
    1,
    Math.ceil(
      (listState.kind === 'success' ? listState.data.total : 0) /
        ADMIN_JOB_PAGE_SIZE,
    ),
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Tin tuyển dụng"
        description="Xem danh sách tất cả tin tuyển dụng trên nền tảng, tìm kiếm và quản lý trạng thái."
      />

      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        aria-label="Tìm kiếm tin tuyển dụng"
      >
        <div className="w-full sm:max-w-xs">
          <Input
            id="admin-job-search"
            name="search"
            type="search"
            placeholder="Tìm theo tiêu đề..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Tìm theo tiêu đề"
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
              icon={<Briefcase className="h-6 w-6" aria-hidden="true" />}
              title="Không tìm thấy tin tuyển dụng"
              description={
                searchQuery
                  ? 'Không có tin tuyển dụng nào khớp với từ khóa hiện tại. Hãy điều chỉnh tìm kiếm để xem thêm kết quả.'
                  : 'Chưa có tin tuyển dụng nào trên nền tảng.'
              }
            />
          ) : (
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[960px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th scope="col" className="px-4 py-3 font-medium">
                        Tiêu đề
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Công ty
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Loại
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Hình thức
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Trạng thái
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Địa điểm
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Ngày tạo
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Thao tác
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {listState.data.items.map((job) => (
                      <tr
                        key={job.id}
                        className="border-b last:border-b-0 hover:bg-muted/40"
                      >
                        <td className="px-4 py-3">
                          <span className="truncate font-medium max-w-[280px] block">
                            {job.title}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="truncate max-w-[160px] block text-muted-foreground">
                            {job.company_name || `Công ty ${job.company_id.slice(0, 8)}`}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={TYPE_BADGE_VARIANT[job.job_type]}>
                            {JOB_TYPE_LABELS[job.job_type]}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="neutral">
                            {WORKPLACE_TYPE_LABELS[job.workplace_type]}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={STATUS_BADGE_VARIANT[job.status]}>
                            {JOB_STATUS_LABELS[job.status]}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {job.location}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatCreatedAt(job.created_at) || 'Không rõ'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => navigate(`/admin/jobs/${job.id}/edit`)}
                              aria-label={`Sửa tin tuyển dụng ${job.title}`}
                            >
                              <Edit className="h-4 w-4" aria-hidden="true" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => navigate(`/admin/jobs/${job.id}/applicants`)}
                              aria-label={`Xem ứng viên ${job.title}`}
                            >
                              <Users className="h-4 w-4" aria-hidden="true" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => handleStatusClick(job)}
                              aria-label={`Đổi trạng thái ${job.title}`}
                              disabled={ALLOWED_STATUS_TRANSITIONS[job.status].length === 0}
                            >
                              <ArrowUpDown className="h-4 w-4" aria-hidden="true" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                              onClick={() => handleDeleteClick(job)}
                              aria-label={`Xóa tin tuyển dụng ${job.title}`}
                            >
                              <Trash2 className="h-4 w-4" aria-hidden="true" />
                            </Button>
                          </div>
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

      {/* Delete Confirmation Dialog */}
      {deleteDialogOpen && (
        <Modal
          onClose={() => setDeleteDialogOpen(false)}
          title="Xóa tin tuyển dụng"
          description={`Bạn có chắc chắn muốn xóa tin tuyển dụng "{jobToDelete?.title}"? Hành động này không thể hoàn tác.`}
          footer={
            <>
              <Button variant="ghost" onClick={() => setDeleteDialogOpen(false)}>
                Hủy
              </Button>
              <Button onClick={handleDeleteConfirm} disabled={deleting}>
                {deleting ? 'Đang xóa...' : 'Xóa'}
              </Button>
            </>
          }
        >
          <p>Xác nhận xóa tin tuyển dụng này?</p>
        </Modal>
      )}

      {/* Status Change Dialog */}
      {statusDialogOpen && (
        <Modal
          onClose={() => setStatusDialogOpen(false)}
          title="Đổi trạng thái tin tuyển dụng"
          description={`Chọn trạng thái mới cho tin tuyển dụng "{jobToStatusChange?.title}".`}
          footer={
            <>
              <Button variant="ghost" onClick={() => setStatusDialogOpen(false)}>
                Hủy
              </Button>
              <Button onClick={handleStatusConfirm} disabled={changingStatus}>
                {changingStatus ? 'Đang cập nhật...' : 'Cập nhật'}
              </Button>
            </>
          }
        >
          <div className="space-y-4">
            <Select
              name="status"
              value={newStatus}
              onChange={(e) => setNewStatus(e.target.value as JobStatus)}
              disabled={changingStatus}
            >
              {ALLOWED_STATUS_TRANSITIONS[jobToStatusChange?.status || 'draft'].map((status) => (
                <option key={status} value={status}>
                  {JOB_STATUS_LABELS[status]}
                </option>
              ))}
            </Select>
            {statusError && (
              <p className="text-sm text-destructive">{statusError}</p>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}