import { PageHeader } from '@/components/common/PageHeader'
import { AdminEmailList } from '@/features/admin/components/AdminEmailList'

export function AdminEmailsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Hàng đợi email"
        description="Theo dõi email thông báo đã phát hành, gửi lại thủ công khi gửi thất bại và kiểm tra các giao dịch còn tồn đọng."
      />

      <AdminEmailList />
    </div>
  )
}
