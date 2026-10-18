import { useState } from 'react'
import { ShieldOff, X } from 'lucide-react'
import { revokeAdminSubscription } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import { getFriendlyErrorMessage } from '@/utils/errors'

export interface RevocableSubscription {
  id: string
  user_email: string | null
  user_id: string
  plan_name: string | null
}

interface AdminSubscriptionRevokeModalProps {
  subscription: RevocableSubscription
  onClose: () => void
  onSuccess: () => void
}

export function AdminSubscriptionRevokeModal({
  subscription,
  onClose,
  onSuccess,
}: AdminSubscriptionRevokeModalProps) {
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleRevoke = async () => {
    if (reason.trim().length < 5) {
      setError('Lý do phải có ít nhất 5 ký tự')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await revokeAdminSubscription(subscription.id, { reason: reason.trim() })
      onSuccess()
      onClose()
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      size="md"
      ariaLabel="Thu hồi gói thuê bao"
      title={
        <span className="flex items-center gap-2">
          <ShieldOff className="h-5 w-5 text-destructive" aria-hidden="true" />
          Thu hồi gói thuê bao
        </span>
      }
      description={`Người dùng: ${subscription.user_email ?? subscription.user_id}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            <X className="h-4 w-4 mr-2" aria-hidden="true" />
            Hủy
          </Button>
          <Button
            variant="destructive"
            onClick={handleRevoke}
            isLoading={submitting}
            disabled={submitting}
          >
            <ShieldOff className="h-4 w-4 mr-2" aria-hidden="true" />
            Xác nhận thu hồi
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-md bg-muted/50 p-4">
          <p className="text-sm text-muted-foreground">
            Gói <strong>{subscription.plan_name ?? '—'}</strong> sẽ bị thu hồi có
            hiệu lực ngay lập tức. Tài khoản người dùng vẫn được giữ nguyên, chỉ
            mất quyền lợi của gói.
          </p>
        </div>

        <div>
          <label htmlFor="revoke-reason" className="block text-sm font-medium mb-1">
            Lý do thu hồi <span className="text-destructive">*</span>
          </label>
          <Textarea
            id="revoke-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Nhập lý do thu hồi (tối thiểu 5 ký tự, tối đa 500 ký tự)..."
            rows={3}
            maxLength={500}
            disabled={submitting}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            {reason.length}/500 ký tự
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
