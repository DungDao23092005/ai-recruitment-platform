import { useState } from 'react'
import { applyJob } from '@/api/applications'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Confirm application"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <Card>
          <CardHeader>
            <CardTitle>Confirm application</CardTitle>
            <CardDescription>
              You are about to apply for the following job.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="font-medium">{job.title}</p>
              <p className="text-sm text-muted-foreground">{job.location}</p>
            </div>

            {success ? (
              <p
                role="status"
                className="rounded-md bg-green-50 px-3 py-2 text-sm font-medium text-green-700"
              >
                Đã nộp đơn thành công
              </p>
            ) : null}

            {error ? (
              <p
                role="alert"
                className="rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-destructive"
              >
                {error}
              </p>
            ) : null}

            {submitting ? (
              <div className="flex items-center justify-center py-2">
                <Spinner size="md" />
              </div>
            ) : null}
          </CardContent>
          <CardFooter className="justify-end gap-2">
            <Button variant="ghost" onClick={onClose} disabled={submitting}>
              Close
            </Button>
            <Button
              onClick={handleConfirm}
              isLoading={submitting}
              disabled={success}
            >
              Confirm application
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  )
}