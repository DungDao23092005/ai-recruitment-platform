import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Building2,
  Calendar,
  CalendarClock,
  Check,
  Clock,
  ExternalLink,
  MapPin,
  Video,
  X,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Skeleton } from '@/components/ui/skeleton'
import { InterviewDeclineModal } from '@/features/candidate/components/InterviewDeclineModal'
import {
  candidateActionInterview,
  listCandidateInterviews,
} from '@/api/interviews'
import { formatDateTime } from '@/utils/datetime'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'
import type {
  CandidateScheduledInterview,
  Interview,
  InterviewStatus,
  InterviewType,
} from '@/types/application'

export type ScheduleFilterKey = 'all' | 'upcoming' | 'past'

const FILTERS: { key: ScheduleFilterKey; label: string }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'upcoming', label: 'Sắp tới' },
  { key: 'past', label: 'Đã qua' },
]

const STATUS_LABELS: Record<InterviewStatus, string> = {
  scheduled: 'Chờ bạn xác nhận',
  candidate_confirmed: 'Bạn đã xác nhận',
  candidate_declined: 'Bạn đã từ chối',
  completed: 'Đã hoàn thành',
  cancelled: 'Đã hủy',
}

const STATUS_CLASSES: Record<InterviewStatus, string> = {
  scheduled:
    'border-amber-500/40 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
  candidate_confirmed:
    'border-emerald-500/40 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300',
  candidate_declined:
    'border-rose-500/40 bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
  completed:
    'border-blue-500/40 bg-blue-50 text-blue-800 dark:bg-blue-950/40 dark:text-blue-300',
  cancelled: 'border-border/60 bg-muted/60 text-muted-foreground',
}

const INTERVIEW_TYPE_LABELS: Record<InterviewType, string> = {
  technical: 'Chuyên môn',
  behavioral: 'Hành vi',
  hr: 'Nhân sự',
  case_study: 'Case Study',
}

export function isUpcomingInterview(
  interview: CandidateScheduledInterview,
  referenceTime = Date.now(),
): boolean {
  const isPendingOrConfirmed =
    interview.status === 'scheduled' ||
    interview.status === 'candidate_confirmed'
  const isTimeNotPassed =
    new Date(interview.scheduled_at).getTime() >= referenceTime
  return isPendingOrConfirmed && isTimeNotPassed
}

export function isPastInterview(
  interview: CandidateScheduledInterview,
  referenceTime = Date.now(),
): boolean {
  if (
    interview.status === 'completed' ||
    interview.status === 'cancelled' ||
    interview.status === 'candidate_declined'
  ) {
    return true
  }
  return new Date(interview.scheduled_at).getTime() < referenceTime
}

export function CandidateInterviewsPage() {
  const navigate = useNavigate()
  const [interviews, setInterviews] = useState<CandidateScheduledInterview[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<ScheduleFilterKey>('all')

  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [decliningInterview, setDecliningInterview] =
    useState<CandidateScheduledInterview | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadInterviews = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await listCandidateInterviews()
      setInterviews(data)
    } catch (loadError) {
      setError(getFriendlyErrorMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadInterviews()
  }, [loadInterviews])

  const filteredInterviews = useMemo(() => {
    const now = Date.now()
    if (filter === 'upcoming') {
      return interviews.filter((item) => isUpcomingInterview(item, now))
    }
    if (filter === 'past') {
      return interviews.filter((item) => isPastInterview(item, now))
    }
    return interviews
  }, [filter, interviews])

  const counts = useMemo(() => {
    const now = Date.now()
    return {
      all: interviews.length,
      upcoming: interviews.filter((item) => isUpcomingInterview(item, now)).length,
      past: interviews.filter((item) => isPastInterview(item, now)).length,
    }
  }, [interviews])

  const handleConfirm = async (interview: CandidateScheduledInterview) => {
    if (confirmingId) return
    setConfirmingId(interview.id)
    setActionError(null)
    setActionSuccess(null)
    try {
      await candidateActionInterview(
        interview.application_id,
        interview.id,
        'confirm',
      )
      setInterviews((prev) =>
        prev.map((item) =>
          item.id === interview.id
            ? { ...item, status: 'candidate_confirmed' as InterviewStatus }
            : item,
        ),
      )
      setActionSuccess('Bạn đã xác nhận tham gia buổi phỏng vấn thành công.')
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setConfirmingId(null)
    }
  }

  const handleDeclined = (updated: Interview) => {
    setInterviews((prev) =>
      prev.map((item) =>
        item.id === updated.id
          ? {
              ...item,
              status: 'candidate_declined' as InterviewStatus,
              candidate_notes: updated.candidate_notes ?? item.candidate_notes,
            }
          : item,
      ),
    )
    setDecliningInterview(null)
    setActionSuccess('Bạn đã từ chối buổi phỏng vấn.')
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Ứng viên"
        title="Lịch phỏng vấn"
        description="Theo dõi và quản lý lịch phỏng vấn cho các vị trí bạn đã ứng tuyển."
      />

      {error ? (
        <ErrorBanner message={error} onRetry={() => void loadInterviews()} />
      ) : null}

      {actionError ? (
        <div
          role="alert"
          className="flex items-center justify-between rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          <span>{actionError}</span>
          <button
            type="button"
            onClick={() => setActionError(null)}
            className="text-xs font-semibold hover:underline"
          >
            Đóng
          </button>
        </div>
      ) : null}

      {actionSuccess ? (
        <div
          role="status"
          className="flex items-center justify-between rounded-lg border border-emerald-500/40 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
        >
          <span>{actionSuccess}</span>
          <button
            type="button"
            onClick={() => setActionSuccess(null)}
            className="text-xs font-semibold hover:underline"
          >
            Đóng
          </button>
        </div>
      ) : null}

      {isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : null}

      {!isLoading && !error && interviews.length === 0 ? (
        <EmptyState
          icon={<CalendarClock className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có lịch phỏng vấn nào"
          description="Khi nhà tuyển dụng lên lịch phỏng vấn, các buổi hẹn sẽ xuất hiện tại đây."
        >
          <Button onClick={() => navigate('/candidate/jobs')}>
            Tìm việc làm ngay
          </Button>
        </EmptyState>
      ) : null}

      {!isLoading && !error && interviews.length > 0 ? (
        <div className="space-y-4">
          <div
            role="group"
            aria-label="Lọc lịch phỏng vấn"
            className="inline-flex flex-wrap gap-1 rounded-lg border border-border/70 bg-muted/40 p-1"
          >
            {FILTERS.map(({ key, label }) => {
              const count = counts[key]
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

          {filteredInterviews.length === 0 ? (
            <EmptyState
              icon={<CalendarClock className="h-6 w-6" aria-hidden="true" />}
              title={
                filter === 'upcoming'
                  ? 'Không có lịch phỏng vấn sắp tới'
                  : 'Không có lịch phỏng vấn đã qua'
              }
              description={
                filter === 'upcoming'
                  ? 'Các buổi phỏng vấn sắp tới sẽ được hiển thị tại đây.'
                  : 'Các buổi phỏng vấn đã hoàn thành hoặc kết thúc sẽ hiển thị tại đây.'
              }
            >
              <Button variant="outline" onClick={() => navigate('/candidate/jobs')}>
                Tìm việc làm ngay
              </Button>
            </EmptyState>
          ) : (
            <div className="space-y-4">
              {filteredInterviews.map((interview) => {
                const canTakeAction = interview.status === 'scheduled'
                const isConfirming = confirmingId === interview.id
                const statusLabel =
                  STATUS_LABELS[interview.status] ?? interview.status
                const statusClass =
                  STATUS_CLASSES[interview.status] ??
                  'border-border/60 bg-muted text-muted-foreground'
                const typeLabel =
                  INTERVIEW_TYPE_LABELS[interview.interview_type] ??
                  interview.interview_type

                return (
                  <Card key={interview.id} className="transition-shadow hover:shadow-sm">
                    <CardContent className="space-y-4 p-5 sm:p-6">
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                        <div className="space-y-1">
                          <h2 className="font-display text-lg font-bold text-foreground">
                            {interview.job_title || 'Buổi phỏng vấn'}
                          </h2>
                          <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                            <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                            <span>{interview.company_name || 'Công ty tuyển dụng'}</span>
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="neutral" className="border-border/80">
                            {typeLabel}
                          </Badge>
                          <span
                            className={cn(
                              'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold',
                              statusClass,
                            )}
                          >
                            {statusLabel}
                          </span>
                        </div>
                      </div>

                      <div className="grid gap-2 text-sm sm:grid-cols-2">
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Calendar className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                          <span>{formatDateTime(interview.scheduled_at)}</span>
                        </div>
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Clock className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                          <span>{interview.duration_minutes} phút</span>
                        </div>
                        {interview.meeting_url ? (
                          <div className="flex items-center gap-2 text-muted-foreground sm:col-span-2">
                            <Video className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                            <a
                              href={interview.meeting_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                            >
                              <span>Tham gia trực tuyến</span>
                              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                            </a>
                          </div>
                        ) : null}
                        {interview.location ? (
                          <div className="flex items-center gap-2 text-muted-foreground sm:col-span-2">
                            <MapPin className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                            <span>{interview.location}</span>
                          </div>
                        ) : null}
                      </div>

                      {interview.candidate_notes ? (
                        <div className="rounded-md border border-border/70 bg-muted/30 p-3 text-xs text-muted-foreground">
                          <span className="font-semibold text-foreground">
                            Ghi chú của bạn:{' '}
                          </span>
                          {interview.candidate_notes}
                        </div>
                      ) : null}

                      {canTakeAction ? (
                        <div className="flex flex-wrap items-center justify-end gap-2 border-t pt-3">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isConfirming}
                            onClick={() => setDecliningInterview(interview)}
                            className="border-destructive/40 text-destructive hover:bg-destructive/10"
                          >
                            <X className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                            Từ chối
                          </Button>
                          <Button
                            size="sm"
                            isLoading={isConfirming}
                            loadingText="Đang xác nhận..."
                            disabled={isConfirming}
                            onClick={() => void handleConfirm(interview)}
                          >
                            <Check className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                            Xác nhận tham gia
                          </Button>
                        </div>
                      ) : null}
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}
        </div>
      ) : null}

      {decliningInterview ? (
        <InterviewDeclineModal
          applicationId={decliningInterview.application_id}
          interview={decliningInterview}
          onClose={() => setDecliningInterview(null)}
          onDeclined={handleDeclined}
        />
      ) : null}
    </div>
  )
}
