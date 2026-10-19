import { useMemo, useState } from 'react'
import { CalendarDays, Eye, Search, User, UserRoundCheck, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ApplicationStatusBadge } from '@/components/common/ApplicationStatusBadge'
import { StatusUpdateModal } from './StatusUpdateModal'
import { ApplicationDetailModal } from './ApplicationDetailModal'
import type { Application, ApplicationStatus } from '@/types/application'

type BoardColumnId =
  | 'applied'
  | 'under_review'
  | 'interviewing'
  | 'offered'
  | 'accepted'
  | 'terminal'

interface BoardColumn {
  id: BoardColumnId
  label: string
  accent: string
}

const BOARD_COLUMNS: BoardColumn[] = [
  { id: 'applied', label: 'Ứng tuyển', accent: 'bg-muted-foreground' },
  { id: 'under_review', label: 'Đang xem xét', accent: 'bg-info' },
  { id: 'interviewing', label: 'Phỏng vấn', accent: 'bg-warning' },
  { id: 'offered', label: 'Đề nghị', accent: 'bg-primary' },
  { id: 'accepted', label: 'Đã tuyển dụng', accent: 'bg-success' },
  { id: 'terminal', label: 'Đã đóng', accent: 'bg-destructive' },
]

const STATUS_TO_COLUMN: Record<ApplicationStatus, BoardColumnId> = {
  applied: 'applied',
  under_review: 'under_review',
  // Legacy status: rendered in the screening column without rewriting the
  // persisted value; the status badge still shows "Lọt vòng ngắn".
  shortlisted: 'under_review',
  interviewing: 'interviewing',
  offered: 'offered',
  accepted: 'accepted',
  rejected: 'terminal',
  withdrawn: 'terminal',
}

function getCandidateDisplayName(application: Application): string {
  const fullName = application.candidate?.full_name
  if (fullName) return fullName
  return `Ứng viên ${application.candidate_id.slice(0, 8)}`
}

function getCandidateTitle(application: Application): string {
  return application.candidate?.title ?? 'Hồ sơ ứng viên'
}

function getSearchText(application: Application): string {
  return [application.candidate?.full_name, application.candidate?.title]
    .filter((value): value is string => Boolean(value))
    .join(' ')
    .toLowerCase()
}

function formatSubmitted(dateString: string): string {
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export interface HiringPipelineBoardProps {
  applications: Application[]
  onStatusChange?: (updated: Application) => void
}

export function HiringPipelineBoard({
  applications,
  onStatusChange,
}: HiringPipelineBoardProps) {
  const [selected, setSelected] = useState<Application | null>(null)
  const [detail, setDetail] = useState<Application | null>(null)
  const [query, setQuery] = useState('')

  const normalizedQuery = query.trim().toLowerCase()
  const hasApplications = applications.length > 0

  // Filter the source applications before grouping so column counts and the
  // empty-search state always reflect the visible set.
  const visibleApplications = useMemo(() => {
    if (!normalizedQuery) return applications
    return applications.filter((application) =>
      getSearchText(application).includes(normalizedQuery),
    )
  }, [applications, normalizedQuery])

  const grouped = useMemo(
    () =>
      BOARD_COLUMNS.map((column) => ({
        column,
        items: visibleApplications.filter(
          (application) => STATUS_TO_COLUMN[application.status] === column.id,
        ),
      })),
    [visibleApplications],
  )

  const noSearchResults = hasApplications && visibleApplications.length === 0

  const clearSearch = () => setQuery('')

  return (
    <div className="space-y-4">
      {hasApplications ? (
        <div className="flex items-center gap-3">
          <div className="relative w-full max-w-sm">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              id="applicant-search"
              name="applicant-search"
              type="search"
              className="pl-9"
              placeholder="Tìm theo tên hoặc chức danh ứng viên..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Tìm ứng viên theo tên hoặc chức danh"
            />
          </div>
          {query ? (
            <Button variant="ghost" size="sm" onClick={clearSearch}>
              <X className="h-4 w-4" aria-hidden="true" />
              Xóa tìm kiếm
            </Button>
          ) : null}
        </div>
      ) : null}

      {noSearchResults ? (
        <div
          role="status"
          className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed bg-muted/20 px-4 py-12 text-center"
        >
          <p className="text-sm font-medium">Không tìm thấy ứng viên phù hợp</p>
          <p className="text-xs text-muted-foreground">
            Không có ứng viên nào khớp với từ khóa &ldquo;{query.trim()}&rdquo;.
          </p>
          <Button variant="outline" size="sm" onClick={clearSearch}>
            <X className="h-4 w-4" aria-hidden="true" />
            Xóa tìm kiếm
          </Button>
        </div>
      ) : (
        <div className="-mx-1 flex gap-4 overflow-x-auto pb-2">
          {grouped.map(({ column, items }) => (
            <section
              key={column.id}
              aria-label={`Cột ${column.label}`}
              className="flex w-[280px] shrink-0 flex-col gap-3 px-1"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${column.accent}`}
                    aria-hidden="true"
                  />
                  {column.label}
                </h3>
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                  {items.length}
                </span>
              </div>

              <div className="flex min-h-[120px] flex-col gap-3 rounded-xl border border-dashed bg-muted/20 p-2">
                {items.length === 0 ? (
                  <p className="px-2 py-6 text-center text-xs italic text-muted-foreground">
                    Không có ứng viên
                  </p>
                ) : (
                  items.map((application) => (
                    <Card
                      key={application.id}
                      className="transition-shadow hover:shadow-soft"
                    >
                      <CardContent className="space-y-3 py-4">
                        <div className="flex items-start gap-3">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                            <User className="h-4 w-4" aria-hidden="true" />
                          </div>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">
                              {getCandidateDisplayName(application)}
                            </p>
                            <p className="truncate text-xs text-muted-foreground">
                              {getCandidateTitle(application)}
                            </p>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <ApplicationStatusBadge status={application.status} />
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <CalendarDays className="h-3 w-3" aria-hidden="true" />
                            {formatSubmitted(application.created_at) ||
                              'Không có ngày nộp đơn'}
                          </span>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setDetail(application)}
                            aria-label={`Xem hồ sơ ứng viên ${application.candidate_id.slice(0, 8)}`}
                          >
                            <Eye className="h-4 w-4" aria-hidden="true" />
                            Xem hồ sơ
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setSelected(application)}
                            aria-label={`Cập nhật trạng thái cho đơn ứng tuyển ${application.id}`}
                            disabled={application.status === 'withdrawn'}
                          >
                            <UserRoundCheck className="h-4 w-4" aria-hidden="true" />
                            Cập nhật
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            </section>
          ))}
        </div>
      )}

      {selected ? (
        <StatusUpdateModal
          application={selected}
          onClose={() => setSelected(null)}
          onSuccess={(updated) => {
            setSelected(null)
            onStatusChange?.(updated)
          }}
        />
      ) : null}

      {detail ? (
        <ApplicationDetailModal
          application={detail}
          onClose={() => setDetail(null)}
          onStatusChange={(updated) => onStatusChange?.(updated)}
        />
      ) : null}
    </div>
  )
}
