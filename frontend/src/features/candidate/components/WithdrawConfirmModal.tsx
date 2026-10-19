import { useState } from 'react'
import { AlertTriangle, Undo2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { withdrawApplication } from '@/api/applications'
import { getFriendlyErrorMessage, isConflictError } from '@/utils/errors'
import type { Application, ApplicationWithJob } from '@/types/application'

export interface WithdrawConfirmModalProps {
  application: ApplicationWithJob
  onClose: () => void
  onSuccess: (updated: Application) => void
  onRefresh?: () => void
}

export function WithdrawConfirmModal({
  application,
  onClose,
  onSuccess,
  onRefresh,
}: WithdrawConfirmModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)

  const handleConfirm = async () => {
    if (submitting || conflict) return
    setSubmitting(true)
    setError(null)
    try {
      const updated = await withdrawApplication(application.id)
      onSuccess(updated)
    } catch (err) {
      if (isConflictError(err)) {
        setConflict(true)
        setError(
          'Đơn ứng tuyển đã được cập nhật ở nơi khác. Vui lòng làm mới để xem trạng thái mới nhất.',
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
      ariaLabel="Xác nhận rút đơn ứng tuyển"
      title={
        <span className="flex items-center gap-2">
          <Undo2 className="h-5 w-5 text-destructive" aria-hidden="true" />
          Rút đơn ứng tuyển
        </span>
      }
      description={application.job_title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            isLoading={submitting}
            loadingText="Đang rút..."
            disabled={conflict}
          >
            Xác nhận rút đơn
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Bạn có chắc muốn rút đơn ứng tuyển cho vị trí{' '}
            <span className="font-semibold">{application.job_title}</span>? Hành
            động này không thể hoàn tác.
          </p>
        </div>

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
