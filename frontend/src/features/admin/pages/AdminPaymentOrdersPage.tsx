import { PageHeader } from '@/components/common/PageHeader'
import { AdminPaymentOrderList } from '@/features/admin/components/AdminPaymentOrderList'

export function AdminPaymentOrdersPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Đơn thanh toán"
        description="Tra cứu và đối soát các đơn thanh toán của doanh nghiệp và ứng viên."
      />
      <AdminPaymentOrderList />
    </div>
  )
}
