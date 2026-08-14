import { useState } from 'react'
import { User } from 'lucide-react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { Application, ApplicationStatus } from '@/types/application'

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: 'Applied',
  under_review: 'Under review',
  shortlisted: 'Shortlisted',
  interviewing: 'Interviewing',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
}

export const APPLICATION_STATUS_OPTIONS: ApplicationStatus[] = [
  'applied',
  'under_review',
  'shortlisted',
  'interviewing',
  'accepted',
  'rejected',
  'withdrawn',
]

export interface StatusUpdateModalProps {
  application: Application
  onClose: () => void
  onSuccess?: (updated: Application) => void
}

export function StatusUpdateModal({
  application,
  onClose,
  onSuccess,
}: StatusUpdateModalProps) {
  const [status, setStatus] = useState<ApplicationStatus>(application.status)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const handleUpdate = async () => {
    setSubmitting(true)
    setError(null)
    setSuccess(false)
    try {
      const updated = await apiClient.patch<Application, Application>(
        `/applications/${application.id}/status`,
        { status },
      )
      setSuccess(true)
      onSuccess?.(updated)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Update application status"
      onClick={onClose}
    >
      <div className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="rounded-lg border bg-background shadow-lg">
          <div className="border-b p-5">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <User className="h-5 w-5 text-primary" aria-hidden="true" />
              Update status
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Application {application.id.slice(0, 8)}
            </p>
          </div>

          <div className="space-y-4 p-5">
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="application-status"
                className="text-sm font-medium leading-none"
              >
                Status
              </label>
              <select
                id="application-status"
                name="status"
                value={status}
                onChange={(e) =>
                  setStatus(e.target.value as ApplicationStatus)
                }
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {APPLICATION_STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {APPLICATION_STATUS_LABELS[option]}
                  </option>
                ))}
              </select>
              <span className="text-xs text-muted-foreground">
                Backend status transitions apply.
              </span>
            </div>

            {success ? (
              <p
                role="status"
                className="rounded-md bg-green-50 px-3 py-2 text-sm font-medium text-green-700"
              >
                Status updated successfully
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
          </div>

          <div className="flex items-center justify-end gap-2 border-t p-4">
            <Button variant="ghost" onClick={onClose} disabled={submitting}>
              Close
            </Button>
            <Button
              onClick={handleUpdate}
              isLoading={submitting}
              disabled={success}
            >
              Save status
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}