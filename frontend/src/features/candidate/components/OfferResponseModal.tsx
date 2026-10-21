import { useState } from 'react'
import { CheckCircle2, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import { respondToOffer } from '@/api/applications'
import { getFriendlyErrorMessage, isConflictError } from '@/utils/errors'
import type {
  Application,
  ApplicationWithJob,
  OfferAction,
} from '@/types/application'

export const OFFER_NOTES_MAX_LENGTH = 1000

export interface OfferResponseModalProps {
  application: ApplicationWithJob
  action: OfferAction
  onClose: () => void
  onSuccess: (updated: Application) => void
  onRefresh?: () => void
}

export function OfferResponseModal({
  application,
  action,
  onClose,
  onSuccess,
  onRefresh,
}: OfferResponseModalProps) {
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isAccept = action === 'accept'

  const handleSubmit = async () => {
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const updated = await respondToOffer(
        application.id,
        action,
        isAccept ? undefined : notes.trim() || undefined,
      )
      onSuccess(updated)
    } catch (err) {
      if (isConflictError(err)) {
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
      ariaLabel={
        isAccept
          ? 'Xác nhận chấp nhận lời mời làm việc'
          : 'Xác nhận từ chối lời mời làm việc'
      }
      title={
        <span className="flex items-center gap-2">
          {isAccept ? (
            <CheckCircle2
              className="h-5 w-5 text-success"
              aria-hidden="true"
            />
          ) : (
            <XCircle
              className="h-5 w-5 text-destructive"
              aria-hidden="true"
            />
          )}
          {isAccept
            ? 'Chấp nhận lời mời làm việc'
            : 'Từ chối lời mời làm việc'}
        </span>
      }
      description={application.job_title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant={isAccept ? 'default' : 'destructive'}
            onClick={handleSubmit}
            isLoading={submitting}
            loadingText="Đang gửi..."
            disabled={submitting}
          >
            {isAccept ? 'Xác nhận chấp nhận' : 'Xác nhận từ chối'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {isAccept
            ? `Bạn sẽ chấp nhận lời mời làm việc cho vị trí ${application.job_title}. Hành động này không thể hoàn tác.`
            : `Bạn sẽ từ chối lời mời làm việc cho vị trí ${application.job_title}. Hành động này không thể hoàn tác.`}
        </p>

        {!isAccept ? (
          <Textarea
            id="offer-decline-notes"
            name="offer-decline-notes"
            label="Lý do từ chối (không bắt buộc)"
            value={notes}
            helperText="Lý do sẽ được gửi tới nhà tuyển dụng."
            maxLength={OFFER_NOTES_MAX_LENGTH}
            onChange={(event) => setNotes(event.target.value)}
          />
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
