import { useState } from 'react'
import { User } from 'lucide-react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Select } from '@/components/ui/select'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { Application, ApplicationStatus } from '@/types/application'

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: 'Đã nộp',
  under_review: 'Đang xem xét',
  shortlisted: 'Lọt vòng ngắn',
  interviewing: 'Đang phỏng vấn',
  accepted: 'Đã chấp nhận',
  rejected: 'Từ chối',
  withdrawn: 'Đã rút',
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
    <Modal
      onClose={onClose}
      size="sm"
      ariaLabel="Cập nhật trạng thái đơn ứng tuyển"
      title={
        <span className="flex items-center gap-2">
          <User className="h-5 w-5 text-primary" aria-hidden="true" />
          Cập nhật trạng thái
        </span>
      }
      description={`Đơn ứng tuyển ${application.id.slice(0, 8)}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Đóng
          </Button>
          <Button
            onClick={handleUpdate}
            isLoading={submitting}
            disabled={success}
          >
            Lưu trạng thái
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Select
          id="application-status"
          name="status"
          label="Trạng thái"
          value={status}
          onChange={(e) => setStatus(e.target.value as ApplicationStatus)}
          helperText="Chuyển trạng thái theo quy trình tuyển dụng của nền tảng."
        >
          {APPLICATION_STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {APPLICATION_STATUS_LABELS[option]}
            </option>
          ))}
        </Select>

        {success ? (
          <p
            role="status"
            className="rounded-md bg-success/10 px-3 py-2 text-sm font-medium text-success"
          >
            Cập nhật trạng thái thành công
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