import { useState } from 'react'
import { Trash2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { deleteAdminPlan } from '@/api/admin'

interface AdminPlanDeleteModalProps {
  planId: string
  planName: string
  onClose: () => void
  onSuccess: () => void
}

export function AdminPlanDeleteModal({
  planId,
  planName,
  onClose,
  onSuccess,
}: AdminPlanDeleteModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDelete = async () => {
    setSubmitting(true)
    setError(null)

    try {
      await deleteAdminPlan(planId)
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
      ariaLabel="Xóa gói tuyển dụng"
      title={
        <span className="flex items-center gap-2">
          <Trash2 className="h-5 w-5 text-destructive" aria-hidden="true" />
          Xóa gói tuyển dụng
        </span>
      }
      description={
        <>
          Bạn đang chuẩn bị xóa gói: <strong>{planName}</strong>. Hành động này không thể hoàn tác.
        </>
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            <X className="h-4 w-4 mr-2" aria-hidden="true" />
            Hủy
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            isLoading={submitting}
            disabled={submitting}
          >
            <Trash2 className="h-4 w-4 mr-2" aria-hidden="true" />
            Xóa gói
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-md bg-muted/50 p-4">
          <p className="text-sm text-muted-foreground">
            <strong>Cảnh báo:</strong> Hành động này sẽ xóa vĩnh viễn gói tuyển dụng khỏi hệ thống.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Chỉ có thể xóa gói khi <strong>không có bất kỳ đăng ký hoặc lịch sử thanh toán nào</strong> liên quan đến gói này.
          </p>
          <div className="mt-3 p-3 rounded-md bg-muted/50">
            <p className="text-sm font-medium">Gói sẽ bị xóa:</p>
            <p className="mt-1 text-sm font-semibold text-primary">{planName}</p>
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-md bg-destructive/10 p-3 text-sm font-medium text-destructive"
          >
            {error}
          </div>
        )}

        <div className="rounded-md bg-muted/50 p-4 text-sm text-muted-foreground">
          <p className="font-medium mb-2">Khuyến nghị:</p>
          <ul className="list-disc list-inside space-y-1">
            <li>Nếu gói đã có người đăng ký hoặc lịch sử thanh toán, hãy sử dụng tính năng <strong>Khóa</strong> để ngừng bán gói thay vì xóa.</li>
            <li>Việc khóa gói sẽ bảo toàn lịch sử đăng ký và thanh toán để tuân thủ quy định.</li>
          </ul>
        </div>
      </div>
    </Modal>
  )
}