import { useCallback, useEffect, useState } from 'react'
import {
  CalendarCheck,
  CalendarClock,
  CalendarX,
  ClipboardList,
  FileText,
  History,
  Pencil,
  RefreshCw,
  Trash2,
  UserMinus,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { EmptyState } from '@/components/ui/empty-state'
import { useAuth } from '@/contexts/AuthContext'
import { listApplicationActivities } from '@/api/applications'
import { getErrorStatus, getFriendlyErrorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/datetime'
import { APPLICATION_STATUS_LABELS } from '@/components/common/ApplicationStatusBadge'
import type { ApplicationActivity, ApplicationStatus } from '@/types/application'

const PAGE_SIZE = 50

type ActivityTone = 'neutral' | 'info' | 'success' | 'warning' | 'destructive'

interface ActionPresentation {
  label: string
  tone: ActivityTone
  icon: LucideIcon
  candidateActor?: boolean
}

const ACTIVITY_PRESENTATION: Record<string, ActionPresentation> = {
  status_changed: { label: 'Cập nhật trạng thái', tone: 'info', icon: RefreshCw },
  candidate_withdrew: {
    label: 'Ứng viên đã rút đơn',
    tone: 'destructive',
    icon: UserMinus,
    candidateActor: true,
  },
  note_added: { label: 'Thêm ghi chú nội bộ', tone: 'neutral', icon: FileText },
  note_updated: { label: 'Cập nhật ghi chú nội bộ', tone: 'neutral', icon: Pencil },
  note_deleted: {
    label: 'Xóa ghi chú nội bộ',
    tone: 'neutral',
    icon: Trash2,
  },
  evaluation_added: {
    label: 'Thêm đánh giá phỏng vấn',
    tone: 'success',
    icon: ClipboardList,
  },
  evaluation_updated: {
    label: 'Cập nhật đánh giá phỏng vấn',
    tone: 'success',
    icon: ClipboardList,
  },
  evaluation_deleted: {
    label: 'Xóa đánh giá phỏng vấn',
    tone: 'neutral',
    icon: Trash2,
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
    label: 'Ứng viên xác nhận phỏng vấn',
    tone: 'success',
    icon: CalendarCheck,
    candidateActor: true,
  },
  interview_declined: {
    label: 'Ứng viên từ chối phỏng vấn',
    tone: 'warning',
    icon: CalendarX,
    candidateActor: true,
  },
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
  return (
    APPLICATION_STATUS_LABELS[status as ApplicationStatus] ?? status
  )
}

function actorLabel(
  actionType: string,
  actorId: string,
  currentUserId: string | undefined,
): string {
  if (ACTIVITY_PRESENTATION[actionType]?.candidateActor) return 'Ứng viên'
  if (currentUserId && actorId === currentUserId) return 'Bạn'
  return 'Đồng nghiệp'
}

export interface ApplicationActivityTimelineProps {
  applicationId: string
}

export function ApplicationActivityTimeline({
  applicationId,
}: ApplicationActivityTimelineProps) {
  const { currentUser } = useAuth()
  const [state, setState] = useState<{
    kind: 'loading' | 'error' | 'success'
    message?: string
    items: ApplicationActivity[]
  }>({ kind: 'loading', items: [] })
  const [limit, setLimit] = useState(PAGE_SIZE)
  const [loadingMore, setLoadingMore] = useState(false)

  const load = useCallback(
    (nextLimit: number) => {
      let active = true
      setState({ kind: 'loading', items: [] })
      listApplicationActivities(applicationId, { limit: nextLimit })
        .then((items) => {
          if (active) setState({ kind: 'success', items })
        })
        .catch((err) => {
          if (active) {
            setState({
              kind: 'error',
              message:
                getErrorStatus(err) === 403
                  ? 'Bạn không có quyền xem lịch sử hoạt động của đơn ứng tuyển này.'
                  : getFriendlyErrorMessage(err),
              items: [],
            })
          }
        })
      return () => {
        active = false
      }
    },
    [applicationId],
  )

  useEffect(() => {
    setLimit(PAGE_SIZE)
    return load(PAGE_SIZE)
  }, [load])

  const handleLoadMore = () => {
    const nextLimit = limit + PAGE_SIZE
    setLimit(nextLimit)
    setLoadingMore(true)
    listApplicationActivities(applicationId, { limit: nextLimit })
      .then((items) => {
        setState({ kind: 'success', items })
      })
      .catch((err) => {
        setState({
          kind: 'error',
          message: getFriendlyErrorMessage(err),
          items: [],
        })
      })
      .finally(() => setLoadingMore(false))
  }

  if (state.kind === 'loading') {
    return (
      <div className="flex items-center justify-center gap-3 py-10 text-muted-foreground">
        <Spinner size="md" />
        <span>Đang tải lịch sử hoạt động...</span>
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <div className="space-y-4 py-4 text-center">
        <p role="alert" className="text-sm font-medium text-destructive">
          {state.message}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setLimit(PAGE_SIZE)
            load(PAGE_SIZE)
          }}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Thử lại
        </Button>
      </div>
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

  return (
    <div className="space-y-4">
      <ol className="space-y-3">
        {state.items.map((item) => {
          const presentation = ACTIVITY_PRESENTATION[item.action_type]
          const Icon = presentation?.icon ?? History
          const label = presentation?.label ?? item.action_type
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
                    {label}
                  </span>
                  {presentation ? (
                    <Badge variant={TONE_BADGE_VARIANT[presentation.tone]}>
                      {actorLabel(item.action_type, item.actor_id, currentUser?.id)}
                    </Badge>
                  ) : null}
                </div>

                {item.action_type === 'status_changed' && (from || to) ? (
                  <div className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                    {from ? <Badge variant="neutral">{from}</Badge> : null}
                    <span aria-hidden="true">→</span>
                    {to ? <Badge variant="info">{to}</Badge> : null}
                  </div>
                ) : null}

                {item.note ? (
                  <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                    {item.note}
                  </p>
                ) : null}

                <p className="text-xs text-muted-foreground">
                  {formatDateTime(item.created_at)}
                </p>
              </div>
            </li>
          )
        })}
      </ol>

      {state.items.length >= limit && state.items.length % PAGE_SIZE === 0 ? (
        <div className="flex justify-center">
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadMore}
            isLoading={loadingMore}
          >
            <Users className="h-4 w-4" aria-hidden="true" />
            Tải thêm hoạt động
          </Button>
        </div>
      ) : null}
    </div>
  )
}
