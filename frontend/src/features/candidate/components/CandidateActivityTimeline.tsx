import { useCallback, useEffect, useRef, useState } from 'react'
import {
  CalendarCheck,
  CalendarClock,
  CalendarX,
  ChevronDown,
  History,
  RefreshCw,
  Undo2,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getMyApplicationTimeline } from '@/api/applications'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/datetime'
import { APPLICATION_STATUS_LABELS } from '@/components/common/ApplicationStatusBadge'
import type { ApplicationStatus, CandidateActivity } from '@/types/application'

export const CANDIDATE_TIMELINE_PAGE_SIZE = 20

type ActivityTone = 'neutral' | 'info' | 'success' | 'warning' | 'destructive'

interface ActionPresentation {
  label: string
  tone: ActivityTone
  icon: LucideIcon
}

// Only candidate-visible activity types are listed. Any other action type
// (e.g. internal notes or evaluations) is collapsed into a safe generic label
// so internal details are never surfaced to the candidate.
const ACTIVITY_PRESENTATION: Record<string, ActionPresentation> = {
  status_changed: {
    label: 'Trạng thái đơn ứng tuyển được cập nhật',
    tone: 'info',
    icon: RefreshCw,
  },
  candidate_withdrew: {
    label: 'Bạn đã rút đơn ứng tuyển',
    tone: 'destructive',
    icon: Undo2,
  },
  interview_scheduled: {
    label: 'Lên lịch phỏng vấn',
    tone: 'info',
    icon: CalendarClock,
  },
  interview_rescheduled: {
    label: 'Đổi lịch phỏng vấn',
    tone: 'info',
    icon: CalendarClock,
  },
  interview_cancelled: {
    label: 'Hủy lịch phỏng vấn',
    tone: 'destructive',
    icon: CalendarX,
  },
  interview_confirmed: {
    label: 'Bạn đã xác nhận phỏng vấn',
    tone: 'success',
    icon: CalendarCheck,
  },
  interview_declined: {
    label: 'Bạn đã từ chối phỏng vấn',
    tone: 'warning',
    icon: CalendarX,
  },
}

const FALLBACK_PRESENTATION: ActionPresentation = {
  label: 'Cập nhật đơn ứng tuyển',
  tone: 'neutral',
  icon: History,
}

const TONE_BADGE_VARIANT: Record<
  ActivityTone,
  'neutral' | 'info' | 'success' | 'warning' | 'destructive'
> = {
  neutral: 'neutral',
  info: 'info',
  success: 'success',
  warning: 'warning',
  destructive: 'destructive',
}

function statusLabel(status: string | null): string | null {
  if (!status) return null
  return APPLICATION_STATUS_LABELS[status as ApplicationStatus] ?? status
}

type TimelineState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; items: CandidateActivity[] }

export interface CandidateActivityTimelineProps {
  applicationId: string
}

export function CandidateActivityTimeline({
  applicationId,
}: CandidateActivityTimelineProps) {
  const [state, setState] = useState<TimelineState>({ kind: 'loading' })
  const [limit, setLimit] = useState(CANDIDATE_TIMELINE_PAGE_SIZE)
  const [loadingMore, setLoadingMore] = useState(false)
  const requestIdRef = useRef(0)

  const load = useCallback(
    (nextLimit: number, mode: 'initial' | 'more') => {
      const requestId = requestIdRef.current + 1
      requestIdRef.current = requestId
      if (mode === 'initial') {
        setState({ kind: 'loading' })
      } else {
        setLoadingMore(true)
      }
      getMyApplicationTimeline(applicationId, { limit: nextLimit })
        .then((items) => {
          if (requestIdRef.current === requestId) {
            setState({ kind: 'success', items })
          }
        })
        .catch((err) => {
          if (requestIdRef.current === requestId) {
            setState({
              kind: 'error',
              message: getFriendlyErrorMessage(err),
            })
          }
        })
        .finally(() => {
          if (requestIdRef.current === requestId && mode === 'more') {
            setLoadingMore(false)
          }
        })
    },
    [applicationId],
  )

  useEffect(() => {
    setLimit(CANDIDATE_TIMELINE_PAGE_SIZE)
    load(CANDIDATE_TIMELINE_PAGE_SIZE, 'initial')
    return () => {
      requestIdRef.current += 1
    }
  }, [load])

  const handleRetry = () => {
    setLimit(CANDIDATE_TIMELINE_PAGE_SIZE)
    load(CANDIDATE_TIMELINE_PAGE_SIZE, 'initial')
  }

  const handleLoadMore = () => {
    const nextLimit = limit + CANDIDATE_TIMELINE_PAGE_SIZE
    setLimit(nextLimit)
    load(nextLimit, 'more')
  }

  if (state.kind === 'loading') {
    return (
      <div className="space-y-2 py-2" aria-busy="true">
        <span className="sr-only">Đang tải lịch sử hoạt động...</span>
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <ErrorBanner
        message={state.message}
        onRetry={handleRetry}
        className="my-2"
      />
    )
  }

  if (state.items.length === 0) {
    return (
      <EmptyState
        icon={<History className="h-6 w-6" aria-hidden="true" />}
        title="Chưa có hoạt động"
        description="Chưa có hoạt động nào được ghi nhận cho đơn ứng tuyển này."
      />
    )
  }

  const canLoadMore = state.items.length >= limit

  return (
    <div className="space-y-4">
      <ol className="space-y-3">
        {state.items.map((item) => {
          const presentation =
            ACTIVITY_PRESENTATION[item.action_type] ?? FALLBACK_PRESENTATION
          const Icon = presentation.icon
          const from = statusLabel(item.from_status)
          const to = statusLabel(item.to_status)

          return (
            <li
              key={item.id}
              className="flex gap-3 rounded-xl border bg-muted/20 px-4 py-3"
            >
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {presentation.label}
                  </span>
                  <Badge variant={TONE_BADGE_VARIANT[presentation.tone]}>
                    Hoạt động
                  </Badge>
                </div>

                {item.action_type === 'status_changed' && (from || to) ? (
                  <div className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                    {from ? <Badge variant="neutral">{from}</Badge> : null}
                    <span aria-hidden="true">→</span>
                    {to ? <Badge variant="info">{to}</Badge> : null}
                  </div>
                ) : null}

                <p className="text-xs text-muted-foreground">
                  {formatDateTime(item.created_at)}
                </p>
              </div>
            </li>
          )
        })}
      </ol>

      {canLoadMore ? (
        <div className="flex justify-center">
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadMore}
            isLoading={loadingMore}
          >
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
            Tải thêm hoạt động
          </Button>
        </div>
      ) : null}
    </div>
  )
}
