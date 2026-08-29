import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { deleteAdminUser } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { AdminUser } from '@/types/admin'

export interface UserDeleteModalProps {
  user: AdminUser
  onClose: () => void
  onSuccess?: (updated: AdminUser) => void
}

export function UserDeleteModal({
  user,
  onClose,
  onSuccess,
}: UserDeleteModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState('')

  const handleDelete = async () => {
    if (confirmation !== user.email) {
      setError('Email xác nhận không khớp. Vui lòng nhập chính xác email của người dùng.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const updated = await deleteAdminUser(user.id)
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
      ariaLabel="Xóa tài khoản người dùng"
      title={
        <span className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden="true" />
          Xóa tài khoản
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
            onClick={handleDelete}
            isLoading={submitting}
          >
            Xóa tài khoản
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-md bg-destructive/10 border border-destructive/20 p-4">
          <p className="text-sm font-medium text-destructive flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            Cảnh báo: Hành động này không thể hoàn tác
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Tài khoản của <strong>{user.email}</strong> sẽ bị xóa vĩnh viễn.
            Email sẽ được ẩn danh thành <code>deleted_{user.id}@anonymized.local</code>.
            Toàn bộ dữ liệu liên quan (hồ sơ, CV, đơn ứng tuyển) vẫn được lưu giữ
            nhưng tài khoản này sẽ không thể đăng nhập hoặc khôi phục.
          </p>
        </div>

        <div>
          <label htmlFor="delete-confirmation" className="block text-sm font-medium mb-1">
            Nhập email để xác nhận: <span className="text-destructive">*</span>
          </label>
          <input
            id="delete-confirmation"
            type="email"
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            placeholder={`Nhập ${user.email} để xác nhận`}
            disabled={submitting}
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Vui lòng nhập chính xác email: <strong>{user.email}</strong>
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
      </div>
    </Modal>
  )
}