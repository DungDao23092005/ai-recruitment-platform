import { useState } from 'react'
import { Unlock } from 'lucide-react'
import { activateAdminUser } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { AdminUser } from '@/types/admin'

export interface UserActivateModalProps {
  user: AdminUser
  onClose: () => void
  onSuccess?: (updated: AdminUser) => void
}

export function UserActivateModal({
  user,
  onClose,
  onSuccess,
}: UserActivateModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleActivate = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const updated = await activateAdminUser(user.id)
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
      ariaLabel="Mở khóa tài khoản người dùng"
      title={
        <span className="flex items-center gap-2">
          <Unlock className="h-5 w-5 text-success" aria-hidden="true" />
          Mở khóa tài khoản
        </span>
      }
      description={`Người dùng: ${user.email}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant="default"
            onClick={handleActivate}
            isLoading={submitting}
          >
            Mở khóa tài khoản
          </Button>
        </>
      }
    >
      <p className="text-sm text-muted-foreground">
        Người dùng sẽ có thể đăng nhập lại vào nền tảng sau khi tài khoản được
        mở khóa.
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