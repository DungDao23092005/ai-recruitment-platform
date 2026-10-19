import { useState } from 'react'
import { CalendarX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import { candidateActionInterview } from '@/api/interviews'
import { getFriendlyErrorMessage, isConflictError } from '@/utils/errors'
import { formatDateTime } from '@/utils/datetime'
import type { Interview, InterviewType } from '@/types/application'

const INTERVIEW_TYPE_LABELS: Record<InterviewType, string> = {
  technical: 'Chuyên môn',
  behavioral: 'Hành vi',
  hr: 'Nhân sự',
  case_study: 'Case Study',
}

export const DECLINE_REASON_MAX_LENGTH = 1000

export interface InterviewDeclineModalProps {
  applicationId: string
  interview: Interview
  onClose: () => void
  onDeclined: (updated: Interview) => void
  onRefresh?: () => void
}

export function InterviewDeclineModal({
  applicationId,
  interview,
  onClose,
  onDeclined,
  onRefresh,
}: InterviewDeclineModalProps) {
  const [reason, setReason] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (submitting) return
    const trimmed = reason.trim()
    if (!trimmed) {
      setFieldError('Vui lòng nhập lý do từ chối.')
      return
    }
    setFieldError(null)
    setError(null)
    setSubmitting(true)
    try {
      const updated = await candidateActionInterview(
        applicationId,
        interview.id,
        'decline',
        trimmed,
      )
      onDeclined(updated)
    } catch (err) {
      if (isConflictError(err)) {
        setError(
          'Buổi phỏng vấn đã được cập nhật ở nơi khác. Vui lòng làm mới để xem thông tin mới nhất.',
        )
        onRefresh?.()
      } else {
        setError(getFriendlyErrorMessage(err))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      size="sm"
      ariaLabel="Từ chối buổi phỏng vấn"
      title={
        <span className="flex items-center gap-2">
          <CalendarX className="h-5 w-5 text-destructive" aria-hidden="true" />
          Từ chối buổi phỏng vấn
        </span>
      }
      description={`${INTERVIEW_TYPE_LABELS[interview.interview_type]} · ${formatDateTime(
        interview.scheduled_at,
      )}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant="destructive"
            onClick={handleSubmit}
            isLoading={submitting}
            loadingText="Đang gửi..."
          >
            Xác nhận từ chối
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Vui lòng cho nhà tuyển dụng biết lý do bạn không thể tham gia buổi
          phỏng vấn này.
        </p>

        <Textarea
          id="decline-reason"
          name="decline-reason"
          label="Lý do từ chối"
          value={reason}
          error={fieldError ?? undefined}
          helperText="Bắt buộc. Lý do sẽ được gửi tới nhà tuyển dụng."
          maxLength={DECLINE_REASON_MAX_LENGTH}
          onChange={(event) => {
            setReason(event.target.value)
            if (fieldError) setFieldError(null)
          }}
          required
        />

        {error ? (
          <p
            role="alert"
            className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
          >
            {error}
          </p>
        ) : null}
      </div>
    </Modal>
  )
}
