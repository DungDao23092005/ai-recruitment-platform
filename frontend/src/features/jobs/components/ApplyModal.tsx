import { useState } from 'react'
import { MapPin, Briefcase } from 'lucide-react'
import { applyJob } from '@/api/applications'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import type { Job } from '@/types/job'

export interface ApplyModalProps {
  job: Job
  onClose: () => void
  onSuccess?: () => void
}

export function ApplyModal({ job, onClose, onSuccess }: ApplyModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleConfirm = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await applyJob(job.id)
      setSuccess(true)
      onSuccess?.()
    } catch (err) {
      const message = getFriendlyErrorMessage(err)
      if (
        err instanceof Error &&
        (err as Error & { response?: { status?: number } }).response?.status ===
          400 &&
        message.includes('already applied')
      ) {
        setError('Bạn đã nộp đơn cho công việc này.')
      } else {
        setError(message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      size="sm"
      ariaLabel="Xác nhận ứng tuyển"
      title="Xác nhận ứng tuyển"
      description="Bạn sắp nộp đơn cho công việc sau:"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Đóng
          </Button>
          <Button
            onClick={handleConfirm}
            isLoading={submitting}
            disabled={success}
          >
            <Briefcase className="h-4 w-4" aria-hidden="true" />
            Xác nhận ứng tuyển
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-xl border bg-muted/30 p-4">
          <p className="font-display font-semibold text-foreground">
            {job.title}
          </p>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            {job.location}
          </p>
        </div>

        {success ? (
          <p
            role="status"
            className="rounded-md bg-success/10 px-3 py-2 text-sm font-medium text-success"
          >
            Đã nộp đơn thành công
          </p>
        ) : null}

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