import { useState } from 'react'
import { UserX } from 'lucide-react'
import { deactivateAdminUser } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
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

  const handleDeactivate = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const updated = await deactivateAdminUser(user.id)
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