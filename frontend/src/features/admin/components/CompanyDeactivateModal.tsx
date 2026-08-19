import { useState } from 'react'
import { Building2 } from 'lucide-react'
import { deleteAdminCompany } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { AdminCompany } from '@/types/admin'

export interface CompanyDeactivateModalProps {
  company: AdminCompany
  onClose: () => void
  onSuccess?: () => void
}

export function CompanyDeactivateModal({
  company,
  onClose,
  onSuccess,
}: CompanyDeactivateModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleLock = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await deleteAdminCompany(company.id)
      onSuccess?.()
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
      ariaLabel="Khóa công ty"
      title={
        <span className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-destructive" aria-hidden="true" />
          Khóa công ty
        </span>
      }
      description={`Công ty: ${company.name}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant="destructive"
            onClick={handleLock}
            isLoading={submitting}
          >
            Khóa công ty
          </Button>
        </>
      }
    >
      <ul className="space-y-2 text-sm text-muted-foreground">
        <li>
          Công ty này sẽ bị vô hiệu hóa và không còn xuất hiện trên nền tảng.
        </li>
        <li>
          Toàn bộ tin tuyển dụng của công ty sẽ bị ẩn khỏi danh sách việc làm
          và kết quả gợi ý.
        </li>
        <li>
          Các tin tuyển dụng này sẽ được gỡ khỏi cơ sở dữ liệu AI để không còn
          được gợi ý cho ứng viên.
        </li>
        <li>
          Dữ liệu đơn ứng tuyển của ứng viên vẫn được giữ nguyên và không bị
          xóa.
        </li>
      </ul>

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