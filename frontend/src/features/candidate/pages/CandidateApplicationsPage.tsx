import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FileText, Search, X } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import { cn } from '@/utils/cn'
import { ApplicationCard } from '@/features/candidate/components/ApplicationCard'
import { useMyApplications } from '@/features/candidate/hooks/useMyApplications'
import type { ApplicationStatus, ApplicationWithJob } from '@/types/application'

type FilterKey = 'all' | 'active' | 'completed'

const ACTIVE_STATUSES: ApplicationStatus[] = [
  'applied',
  'under_review',
  'shortlisted',
  'interviewing',
  'offered',
]

const COMPLETED_STATUSES: ApplicationStatus[] = [
  'accepted',
  'rejected',
  'withdrawn',
]

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'active', label: 'Đang xử lý' },
  { key: 'completed', label: 'Đã kết thúc' },
]

function matchesFilter(status: ApplicationStatus, filter: FilterKey): boolean {
  if (filter === 'active') return ACTIVE_STATUSES.includes(status)
  if (filter === 'completed') return COMPLETED_STATUSES.includes(status)
  return true
}

function matchesQuery(
  application: ApplicationWithJob,
  normalizedQuery: string,
): boolean {
  if (!normalizedQuery) return true
  const haystack = `${application.job_title} ${application.company_name ?? ''}`.toLowerCase()
  return haystack.includes(normalizedQuery)
}

export function CandidateApplicationsPage() {
  const { applications, isLoading, error, refresh } = useMyApplications()
  const [filter, setFilter] = useState<FilterKey>('all')
  const [query, setQuery] = useState('')

  const normalizedQuery = query.trim().toLowerCase()
  const hasSearchOrFilter =
    filter !== 'all' || normalizedQuery.length > 0
  const filteredApplications = applications.filter(
    (application) =>
      matchesFilter(application.status, filter) &&
      matchesQuery(application, normalizedQuery),
  )

  const handleApplicationUpdated = () => {
    refresh()
  }

  const clearSearchAndFilters = () => {
    setFilter('all')
    setQuery('')
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Ứng viên"
        title="Đơn ứng tuyển của tôi"
        description="Theo dõi các vị trí bạn đã ứng tuyển."
      />

      {isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : null}

      {error ? <ErrorBanner message={error} onRetry={refresh} /> : null}

      {!isLoading && !error && applications.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-6 w-6" aria-hidden="true" />}
          title="Bạn chưa có đơn ứng tuyển"
          description="Hãy khám phá các công việc phù hợp và nộp đơn để theo dõi trạng thái tại đây."
        >
          <Link to="/candidate/jobs">
            <Button>
              <Search className="h-4 w-4" aria-hidden="true" />
              Khám phá việc làm
            </Button>
          </Link>
        </EmptyState>
      ) : null}

      {!isLoading && !error && applications.length > 0 ? (
        <div className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div
              role="group"
              aria-label="Lọc đơn ứng tuyển"
              className="inline-flex flex-wrap gap-1 rounded-lg border border-border/70 bg-muted/40 p-1"
            >
              {FILTERS.map(({ key, label }) => {
                const count = applications.filter((application) =>
                  matchesFilter(application.status, key),
                ).length
                const isActive = filter === key
                return (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={isActive}
                    onClick={() => setFilter(key)}
                    className={cn(
                      'rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                      isActive
                        ? 'bg-background text-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {label}
                    <span className="ml-1.5 text-xs text-muted-foreground">
                      ({count})
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="relative w-full sm:max-w-xs">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                type="search"
                name="candidate-application-search"
                aria-label="Tìm kiếm đơn ứng tuyển theo vị trí hoặc công ty"
                placeholder="Tìm theo vị trí hoặc công ty"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className={cn('pl-9', query ? 'pr-9' : undefined)}
              />
              {query ? (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  aria-label="Xóa tìm kiếm"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              ) : null}
            </div>
          </div>

          {filteredApplications.length === 0 ? (
            <EmptyState
              icon={<Search className="h-6 w-6" aria-hidden="true" />}
              title="Không tìm thấy đơn ứng tuyển phù hợp"
              description="Thử từ khóa khác hoặc xóa bộ lọc để xem tất cả đơn ứng tuyển."
            >
              <Button variant="outline" onClick={clearSearchAndFilters}>
                Xóa bộ lọc
              </Button>
            </EmptyState>
          ) : (
            <div className="space-y-4" data-testid="candidate-application-list">
              {filteredApplications.map((application) => (
                <ApplicationCard
                  key={application.id}
                  application={application}
                  onUpdated={handleApplicationUpdated}
                />
              ))}
            </div>
          )}

          {hasSearchOrFilter ? (
            <p role="status" className="sr-only">
              Hiển thị {filteredApplications.length} trong tổng số{' '}
              {applications.length} đơn ứng tuyển.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
