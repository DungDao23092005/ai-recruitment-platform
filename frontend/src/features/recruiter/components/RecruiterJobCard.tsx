import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  MapPin,
  Users,
  Sparkles,
  FileQuestion,
  ChevronRight,
  Pencil,
  Trash2,
  Megaphone,
  XCircle,
  RotateCcw,
} from 'lucide-react'
import apiClient from '@/api/client'
import { Badge } from '@/components/ui/badge'
import type { BadgeProps } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  WORKPLACE_TYPE_LABELS,
} from '@/types/job'
import type { Job, JobStatus } from '@/types/job'
import { cn } from '@/utils/cn'
import { getFriendlyErrorMessage } from '@/utils/errors'

export interface RecruiterJobCardProps {
  job: Job
  onMutated?: () => void
}

type PendingAction = 'close' | 'delete' | null

function companyMonogram(companyName: string): string {
  const trimmed = companyName.trim()
  if (!trimmed) {
    return 'C'
  }
  const words = trimmed.split(/\s+/)
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase()
  }
  return (
    words
      .slice(0, 2)
      .map((word) => word[0])
      .join('')
      .toUpperCase()
  )
}

const JOB_STATUS_VARIANT: Record<JobStatus, NonNullable<BadgeProps['variant']>> = {
  draft: 'neutral',
  published: 'success',
  closed: 'warning',
  expired: 'destructive',
}

export function RecruiterJobCard({ job, onMutated }: RecruiterJobCardProps) {
  const companyLabel = job.company_name
    ? `Công ty: ${job.company_name}`
    : `Công ty: ${job.company_id.slice(0, 8)}`

  const [pendingAction, setPendingAction] = useState<PendingAction>(null)
  const [busyAction, setBusyAction] = useState<'publish' | 'reopen' | null>(
    null,
  )
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const isExpired = job.status === 'expired'
  const statusAction =
    job.status === 'draft' ? ('publish' as const) : job.status === 'closed' ? ('reopen' as const) : null

  const runStatusAction = async () => {
    if (!statusAction) {
      return
    }
    setBusyAction(statusAction)
    setActionError(null)
    try {
      await apiClient.patch<Job, Job>(`/jobs/mine/${job.id}/status`, {
        status: 'published',
      })
      onMutated?.()
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setBusyAction(null)
    }
  }

  const confirmClose = async () => {
    setSubmitting(true)
    setActionError(null)
    try {
      await apiClient.patch<Job, Job>(`/jobs/mine/${job.id}/status`, {
        status: 'closed',
      })
      setPendingAction(null)
      onMutated?.()
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const confirmDelete = async () => {
    setSubmitting(true)
    setActionError(null)
    try {
      await apiClient.delete<void, void>(`/jobs/mine/${job.id}`)
      setPendingAction(null)
      onMutated?.()
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const showClose = job.status === 'published'

  return (
    <Card className="flex h-full flex-col border-border/70 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft">
      <CardHeader className="gap-2.5">
        <div className="flex items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 font-display text-sm font-bold text-primary ring-1 ring-primary/15"
            aria-hidden="true"
          >
            {companyMonogram(job.company_name ?? `Công ty ${job.company_id.slice(0, 8)}`)}
          </div>
          <div className="min-w-0 flex-1">
            <CardTitle className="line-clamp-1 font-display text-lg font-semibold text-foreground">
              {job.title}
            </CardTitle>
            <p className="mt-0.5 truncate text-sm text-muted-foreground">
              {companyLabel}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={JOB_STATUS_VARIANT[job.status]}>
            {JOB_STATUS_LABELS[job.status]}
          </Badge>
          <Badge variant="neutral">{JOB_TYPE_LABELS[job.job_type]}</Badge>
          <Badge variant="neutral">
            {WORKPLACE_TYPE_LABELS[job.workplace_type]}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            {job.location}
          </span>
        </div>
      </CardContent>
      <CardFooter className="flex-col gap-2">
        {actionError ? (
          <p role="alert" className="w-full text-sm font-medium text-destructive">
            {actionError}
          </p>
        ) : null}

        <div className="grid w-full grid-cols-2 gap-2">
          <Link
            to={`/recruiter/jobs/${job.id}/edit`}
            className={cn(buttonVariants({ variant: 'outline' }), 'w-full')}
          >
            <Pencil className="h-4 w-4" aria-hidden="true" />
            Sửa
          </Link>

          {statusAction != null ? (
            <Button
              variant="outline"
              onClick={() => void runStatusAction()}
              isLoading={busyAction === statusAction}
              disabled={busyAction != null}
            >
              {statusAction === 'publish' ? (
                <Megaphone className="h-4 w-4" aria-hidden="true" />
              ) : (
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
              )}
              {statusAction === 'publish' ? 'Đăng tin' : 'Mở lại'}
            </Button>
          ) : null}

          {showClose ? (
            <Button
              variant="outline"
              onClick={() => setPendingAction('close')}
              disabled={busyAction != null}
            >
              <XCircle className="h-4 w-4" aria-hidden="true" />
              Đóng tin
            </Button>
          ) : null}

          {isExpired ? (
            <div
              className={cn(
                buttonVariants({ variant: 'outline' }),
                'pointer-events-none w-full cursor-not-allowed opacity-60',
              )}
            >
              {JOB_STATUS_LABELS.expired}
            </div>
          ) : null}

          <Button
            variant="outline"
            onClick={() => setPendingAction('delete')}
            disabled={busyAction != null}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Xóa
          </Button>
        </div>

        <Link
          to={`/recruiter/jobs/${job.id}/applicants`}
          className={cn(buttonVariants({ variant: 'outline' }), 'w-full')}
        >
          <Users className="h-4 w-4" aria-hidden="true" />
          Xem ứng viên
        </Link>
        <Link
          to={`/recruiter/jobs/${job.id}/recommendations`}
          className={cn(buttonVariants({ variant: 'outline' }), 'w-full')}
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Gợi ý ứng viên AI
        </Link>
        <Link
          to={`/recruiter/jobs/${job.id}/interview`}
          className={cn(buttonVariants({ variant: 'default' }), 'w-full')}
        >
          <FileQuestion className="h-4 w-4" aria-hidden="true" />
          Bộ câu hỏi phỏng vấn
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </CardFooter>

      {pendingAction === 'close' ? (
        <Modal
          onClose={() => setPendingAction(null)}
          size="sm"
          ariaLabel="Đóng tin tuyển dụng"
          title={
            <span className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-warning" aria-hidden="true" />
              Đóng tin tuyển dụng
            </span>
          }
          description="Tin tuyển dụng sẽ không còn hiển thị công khai. Ứng viên đã nộp vẫn được giữ nguyên."
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => setPendingAction(null)}
                disabled={submitting}
              >
                Hủy
              </Button>
              <Button onClick={() => void confirmClose()} isLoading={submitting}>
                Đóng tin
              </Button>
            </>
          }
        >
          <p className="text-sm text-muted-foreground">
            Bạn có thể mở lại tin tuyển dụng này bất cứ lúc nào từ danh sách.
          </p>
        </Modal>
      ) : null}

      {pendingAction === 'delete' ? (
        <Modal
          onClose={() => setPendingAction(null)}
          size="sm"
          ariaLabel="Xóa tin tuyển dụng"
          title={
            <span className="flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-destructive" aria-hidden="true" />
              Xóa tin tuyển dụng
            </span>
          }
          description="Tin tuyển dụng sẽ bị ẩn khỏi danh sách việc làm công khai."
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => setPendingAction(null)}
                disabled={submitting}
              >
                Hủy
              </Button>
              <Button
                variant="destructive"
                onClick={() => void confirmDelete()}
                isLoading={submitting}
              >
                Xóa tin
              </Button>
            </>
          }
        >
          <p className="text-sm text-muted-foreground">
            Hồ sơ của ứng viên vẫn được lưu giữ. Thao tác này không thể hoàn tác
            từ giao diện.
          </p>
        </Modal>
      ) : null}
    </Card>
  )
}