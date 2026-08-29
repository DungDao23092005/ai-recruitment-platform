import { useState } from 'react'
import { UserX } from 'lucide-react'
import { deactivateAdminUser } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { AdminUser } from '@/types/admin'

export interface UserDeactivateModalProps {
  user: AdminUser
  onClose: () => void
  onSuccess?: (updated: AdminUser) => void
}

export function UserDeactivateModal({
  user,
  onClose,
  onSuccess,
}: UserDeactivateModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  const handleDeactivate = async () => {
    if (!reason.trim()) {
      setError('Lý do khóa tài khoản là bắt buộc')
      return
    }
    if (reason.length > 500) {
      setError('Lý do không được vượt quá 500 ký tự')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const updated = await deactivateAdminUser(user.id, { reason: reason.trim() })
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
      ariaLabel="Khóa tài khoản người dùng"
      title={
        <span className="flex items-center gap-2">
          <UserX className="h-5 w-5 text-destructive" aria-hidden="true" />
          Khóa tài khoản
        </span>
      }
      description={`Người dùng: ${user.email}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant="destructive"
            onClick={handleDeactivate}
            isLoading={submitting}
          >
            Khóa tài khoản
          </Button>
        </>
      }
    >
      <p className="text-sm text-muted-foreground">
        Người dùng này sẽ không thể đăng nhập vào nền tảng sau khi tài khoản
        bị khóa. Toàn bộ dữ liệu của họ (hồ sơ, CV, đơn ứng tuyển) vẫn được
        lưu giữ và không bị xóa.
      </p>

      <div className="mt-4">
        <label htmlFor="deactivate-reason" className="block text-sm font-medium mb-1">
          Lý do khóa tài khoản <span className="text-destructive">*</span>
        </label>
        <Textarea
          id="deactivate-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Nhập lý do khóa tài khoản (tối đa 500 ký tự)..."
          rows={4}
          maxLength={500}
          disabled={submitting}
          className="mt-1"
        />
        <p className="mt-1 text-xs text-muted-foreground">
          {reason.length}/500 ký tự
        </p>
      </div>

      {error ? (
        <p
          role="alert"
          className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
        >
          {error}
        </p>
      ) : null}
    </Modal>
  )
}