import { useState } from 'react'
import { PageHeader } from '@/components/common/PageHeader'
import { AdminSubscriptionList } from '@/features/admin/components/AdminSubscriptionList'
import { AdminSubscriptionChangePlanModal } from '@/features/admin/components/AdminSubscriptionChangePlanModal'
import { AdminSubscriptionRevokeModal } from '@/features/admin/components/AdminSubscriptionRevokeModal'
import { AdminSubscriptionDetailModal } from '@/features/admin/components/AdminSubscriptionDetailModal'
import type { AdminSubscriptionListItem } from '@/types/admin'

type Dialog =
  | { kind: 'change-plan'; subscription: AdminSubscriptionListItem }
  | { kind: 'revoke'; subscription: AdminSubscriptionListItem }
  | { kind: 'detail'; subscription: AdminSubscriptionListItem }
  | null

export function AdminSubscriptionsPage() {
  const [dialog, setDialog] = useState<Dialog>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleSuccess = () => {
    setRefreshKey((value) => value + 1)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Thuê bao người dùng"
        description="Xem, đổi gói và thu hồi gói dịch vụ của người dùng, kèm lịch sử thao tác."
      />

      <AdminSubscriptionList
        key={refreshKey}
        onChangePlan={(subscription) => setDialog({ kind: 'change-plan', subscription })}
        onRevoke={(subscription) => setDialog({ kind: 'revoke', subscription })}
        onViewDetail={(subscription) => setDialog({ kind: 'detail', subscription })}
      />

      {dialog?.kind === 'change-plan' ? (
        <AdminSubscriptionChangePlanModal
          subscription={dialog.subscription}
          onClose={() => setDialog(null)}
          onSuccess={handleSuccess}
        />
      ) : null}

      {dialog?.kind === 'revoke' ? (
        <AdminSubscriptionRevokeModal
          subscription={dialog.subscription}
          onClose={() => setDialog(null)}
          onSuccess={handleSuccess}
        />
      ) : null}

      {dialog?.kind === 'detail' ? (
        <AdminSubscriptionDetailModal
          subscription={dialog.subscription}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  )
}
