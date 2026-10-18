import { useEffect, useState } from 'react'
import { AlertTriangle, FileText, RefreshCw, ShieldOff, X } from 'lucide-react'
import { getAdminSubscription } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import {
  formatSubscriptionDate,
  SubscriptionStatusBadge,
} from '@/features/admin/components/AdminSubscriptionList'
import { AdminSubscriptionRevokeModal } from '@/features/admin/components/AdminSubscriptionRevokeModal'
import type {
  AdminSubscriptionAuditAction,
  AdminSubscriptionDetail,
  AdminSubscriptionListItem,
  AdminSubscriptionSummary,
} from '@/types/admin'

const ACTION_LABELS: Record<AdminSubscriptionAuditAction, string> = {
  provision: 'Khởi tạo',
  change_plan: 'Đổi gói',
  revoke: 'Thu hồi',
}

type DetailState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; data: AdminSubscriptionDetail }

interface AdminSubscriptionDetailModalProps {
  subscription: AdminSubscriptionListItem
  onClose: () => void
  onRevoked?: () => void
}

function formatAmount(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency: currency || 'VND',
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return `${amount} ${currency}`
  }
}

export function AdminSubscriptionDetailModal({
  subscription,
  onClose,
  onRevoked,
}: AdminSubscriptionDetailModalProps) {
  const [state, setState] = useState<DetailState>({ kind: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)
  const [revokeTarget, setRevokeTarget] = useState<AdminSubscriptionSummary | null>(
    null,
  )

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setState({ kind: 'loading' })
      try {
        const data = await getAdminSubscription(subscription.id)
        if (!cancelled) setState({ kind: 'success', data })
      } catch (err) {
        if (!cancelled) {
          setState({ kind: 'error', message: getFriendlyErrorMessage(err) })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [subscription.id, reloadKey])

  const detail = state.kind === 'success' ? state.data.subscription : subscription

  const handleRevoked = () => {
    setRevokeTarget(null)
    setReloadKey((value) => value + 1)
    onRevoked?.()
  }

  return (
    <Modal
      onClose={onClose}
      size="lg"
      ariaLabel="Chi tiết thuê bao"
      title={
        <span className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
          Chi tiết thuê bao
        </span>
      }
      description={`Người dùng: ${detail.user_email ?? detail.user_id}`}
      footer={
        <Button variant="ghost" onClick={onClose}>
          <X className="h-4 w-4 mr-2" aria-hidden="true" />
          Đóng
        </Button>
      }
    >
      {state.kind === 'loading' ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-8 w-full" />
          ))}
        </div>
      ) : null}

      {state.kind === 'error' ? (
        <ErrorBanner message={state.message} />
      ) : null}

      {state.kind === 'success' ? (
        <div className="space-y-6">
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Gói đại diện</dt>
              <dd className="text-sm font-medium">{detail.plan_name ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Trạng thái</dt>
              <dd className="mt-1">
                <SubscriptionStatusBadge status={detail.effective_status} />
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Tổng số thuê bao</dt>
              <dd className="text-sm">{detail.total_subscriptions}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Bắt đầu</dt>
              <dd className="text-sm">{formatSubscriptionDate(detail.started_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Hết hạn</dt>
              <dd className="text-sm">{formatSubscriptionDate(detail.expires_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Tin tuyển dụng</dt>
              <dd className="text-sm">
                {detail.job_posts_used} / {detail.max_job_posts}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Tìm kiếm ứng viên</dt>
              <dd className="text-sm">
                {detail.candidate_searches_used} / {detail.max_candidate_searches}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Tính năng AI</dt>
              <dd className="text-sm">
                {detail.ai_features_used} / {detail.max_ai_features}
              </dd>
            </div>
          </dl>

          {detail.is_entitlement_incident ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4" aria-hidden="true" />
              <div>
                <p className="font-medium">Sự cố quyền lợi</p>
                <p className="text-xs">
                  Người dùng có giao dịch đã thanh toán nhưng gói chưa được kích
                  hoạt.
                  {detail.incident_internal_order_id
                    ? ` Mã đơn: ${detail.incident_internal_order_id}.`
                    : ''}
                  {detail.incident_amount != null
                    ? ` Số tiền: ${formatAmount(detail.incident_amount, 'VND')}.`
                    : ''}{' '}
                  Cần xử lý trước khi đổi gói hoặc thu hồi.
                </p>
              </div>
            </div>
          ) : null}

          {detail.has_multiple_active ? (
            <div
              role="status"
              className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-warning"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4" aria-hidden="true" />
              <div>
                <p className="font-medium">Nhiều gói đang hoạt động</p>
                <p className="text-xs">
                  Người dùng có nhiều hơn một gói đang hoạt động. Chỉ có thể thao
                  tác khi còn một gói hoặc xử lý từng thuê bao bên dưới.
                </p>
              </div>
            </div>
          ) : null}

          <div>
            <h3 className="mb-2 text-sm font-semibold">Lịch sử thay đổi (audit trail)</h3>
            {state.data.audit_logs.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Chưa có thao tác quản trị nào được ghi nhận.
              </p>
            ) : (
              <ul className="space-y-2" aria-label="Lịch sử thay đổi thuê bao">
                {state.data.audit_logs.map((log) => (
                  <li
                    key={log.id}
                    className="rounded-md border p-3 text-sm"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">{ACTION_LABELS[log.action] ?? log.action}</span>
                      <span className="text-xs text-muted-foreground">
                        {formatSubscriptionDate(log.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-muted-foreground">{log.reason}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Quản trị viên: {log.admin_email ?? log.admin_id}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold">Các thuê bao của người dùng</h3>
            {state.data.history.length === 0 ? (
              <p className="text-sm text-muted-foreground">Không có dữ liệu.</p>
            ) : (
              <ul className="space-y-2" aria-label="Danh sách thuê bao của người dùng">
                {state.data.history.map((item) => {
                  const revocable =
                    item.status === 'active' || item.status === 'pending'
                  const blocked = detail.has_unresolved_payment
                  return (
                    <li key={item.id} className="rounded-md border p-3 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium">{item.plan_name ?? '—'}</span>
                        <span className="flex items-center gap-2">
                          <SubscriptionStatusBadge status={item.status} />
                          <span className="text-xs text-muted-foreground">
                            {formatSubscriptionDate(item.expires_at)}
                          </span>
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Mã thuê bao: {item.id}
                      </p>
                      {item.payments.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {item.payments.map((payment) => (
                            <li
                              key={payment.id}
                              className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"
                            >
                              <span>{payment.internal_order_id}</span>
                              <span>
                                {formatAmount(payment.amount, payment.currency)} ·{' '}
                                {payment.status} ·{' '}
                                {formatSubscriptionDate(payment.paid_at)}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      {revocable ? (
                        <div className="mt-2 flex justify-end">
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            disabled={blocked}
                            title={
                              blocked
                                ? 'Không thể thu hồi khi người dùng còn giao dịch chưa xử lý.'
                                : undefined
                            }
                            aria-label={`Thu hồi thuê bao ${item.id}`}
                            onClick={() => setRevokeTarget(item)}
                          >
                            <ShieldOff className="h-4 w-4 mr-1" aria-hidden="true" />
                            Thu hồi
                          </Button>
                        </div>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      ) : null}

      {state.kind === 'loading' ? (
        <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
          Đang tải chi tiết...
        </div>
      ) : null}

      {revokeTarget ? (
        <AdminSubscriptionRevokeModal
          subscription={{
            id: revokeTarget.id,
            user_email: detail.user_email,
            user_id: detail.user_id,
            plan_name: revokeTarget.plan_name,
          }}
          onClose={() => setRevokeTarget(null)}
          onSuccess={handleRevoked}
        />
      ) : null}
    </Modal>
  )
}
