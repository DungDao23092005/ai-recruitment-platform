import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FileText, Search, X } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import { cn } from '@/utils/cn'
import { getMyApplication } from '@/api/applications'
import { getFriendlyErrorMessage, isNotFoundError } from '@/utils/errors'
import { ApplicationCard } from '@/features/candidate/components/ApplicationCard'
import { useMyApplications } from '@/features/candidate/hooks/useMyApplications'
import type { ApplicationStatus, ApplicationWithJob } from '@/types/application'

const TARGET_NOT_FOUND_MESSAGE =
  'Đơn ứng tuyển này không tồn tại hoặc đã bị xóa.'

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
  const [searchParams] = useSearchParams()
  const targetId = searchParams.get('id')?.trim() || null

  const [filter, setFilter] = useState<FilterKey>('all')
  const [query, setQuery] = useState('')
  const [targetApplication, setTargetApplication] =
    useState<ApplicationWithJob | null>(null)
  const [targetError, setTargetError] = useState<string | null>(null)
  const [isTargetLoading, setIsTargetLoading] = useState(false)
  const [targetRetryKey, setTargetRetryKey] = useState(0)
  const [highlightedApplicationId, setHighlightedApplicationId] = useState<
    string | null
  >(null)

  const targetRequestIdRef = useRef(0)
  const attemptedTargetIdRef = useRef<string | null>(null)
  const highlightedTargetIdRef = useRef<string | null>(null)

  useEffect(() => {
    targetRequestIdRef.current += 1
    attemptedTargetIdRef.current = null
    highlightedTargetIdRef.current = null
    setTargetApplication(null)
    setTargetError(null)
    setIsTargetLoading(Boolean(targetId))
    setHighlightedApplicationId(null)
    setFilter('all')
  }, [targetId])

  useEffect(() => {
    if (!targetId || isLoading) return

    if (applications.some((application) => application.id === targetId)) {
      attemptedTargetIdRef.current = targetId
      setIsTargetLoading(false)
      setTargetError(null)
      return
    }

    if (attemptedTargetIdRef.current === targetId) return

    attemptedTargetIdRef.current = targetId
    const requestId = targetRequestIdRef.current + 1
    targetRequestIdRef.current = requestId
    setIsTargetLoading(true)
    setTargetError(null)

    void getMyApplication(targetId)
      .then((application) => {
        if (targetRequestIdRef.current !== requestId) return
        setTargetApplication(application)
        setIsTargetLoading(false)
      })
      .catch((err) => {
        if (targetRequestIdRef.current !== requestId) return
        setTargetError(
          isNotFoundError(err)
            ? TARGET_NOT_FOUND_MESSAGE
            : getFriendlyErrorMessage(err),
        )
        setIsTargetLoading(false)
      })
  }, [applications, isLoading, targetId, targetRetryKey])

  const retryTarget = useCallback(() => {
    if (!targetId) return
    attemptedTargetIdRef.current = null
    setTargetError(null)
    setIsTargetLoading(true)
    setTargetRetryKey((key) => key + 1)
  }, [targetId])

  const allApplications = useMemo(() => {
    if (!targetApplication) return applications
    if (
      applications.some(
        (application) => application.id === targetApplication.id,
      )
    ) {
      return applications
    }
    return [...applications, targetApplication]
  }, [applications, targetApplication])

  const normalizedQuery = query.trim().toLowerCase()
  const hasSearchOrFilter =
    filter !== 'all' || normalizedQuery.length > 0
  const filteredApplications = allApplications.filter(
    (application) =>
      matchesFilter(application.status, filter) &&
      matchesQuery(application, normalizedQuery),
  )

  const targetCardRendered = Boolean(
    targetId &&
      filteredApplications.some(
        (application) => application.id === targetId,
      ),
  )

  useEffect(() => {
    if (
      !targetId ||
      !targetCardRendered ||
      highlightedTargetIdRef.current === targetId
    ) {
      return
    }

    highlightedTargetIdRef.current = targetId
    const frame = requestAnimationFrame(() => {
      const element = document.getElementById(`application-${targetId}`)
      if (!element) return
      element.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
      setHighlightedApplicationId(targetId)
    })
    const timer = window.setTimeout(() => {
      setHighlightedApplicationId(null)
    }, 3000)

    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(timer)
    }
  }, [targetCardRendered, targetId])

  const handleApplicationUpdated = () => {
    refresh()
    if (
      targetId &&
      !applications.some((application) => application.id === targetId)
    ) {
      attemptedTargetIdRef.current = null
      setTargetRetryKey((key) => key + 1)
    }
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

      {targetError ? (
        <ErrorBanner message={targetError} onRetry={retryTarget} />
      ) : null}

      {isTargetLoading && !isLoading ? (
        <div
          role="status"
          className="flex items-center gap-2 rounded-lg border border-border/70 bg-muted/30 px-4 py-3 text-sm text-muted-foreground"
        >
          <Spinner size="sm" />
          Đang tải đơn ứng tuyển...
        </div>
      ) : null}

      {!isLoading && !error && allApplications.length === 0 ? (
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

      {!isLoading && !error && allApplications.length > 0 ? (
        <div className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div
              role="group"
              aria-label="Lọc đơn ứng tuyển"
              className="inline-flex flex-wrap gap-1 rounded-lg border border-border/70 bg-muted/40 p-1"
            >
              {FILTERS.map(({ key, label }) => {
                const count = allApplications.filter((application) =>
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
                  highlighted={highlightedApplicationId === application.id}
                  onUpdated={handleApplicationUpdated}
                />
              ))}
            </div>
          )}

          {hasSearchOrFilter ? (
            <p role="status" className="sr-only">
              Hiển thị {filteredApplications.length} trong tổng số{' '}
              {allApplications.length} đơn ứng tuyển.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
