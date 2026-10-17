import { useEffect, useState } from 'react'
import { Sparkles, X } from 'lucide-react'
import { changeAdminSubscriptionPlan, getAdminPlans } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { AdminPlanRead, AdminSubscriptionListItem } from '@/types/admin'

interface AdminSubscriptionChangePlanModalProps {
  subscription: AdminSubscriptionListItem
  onClose: () => void
  onSuccess: () => void
}

export function AdminSubscriptionChangePlanModal({
  subscription,
  onClose,
  onSuccess,
}: AdminSubscriptionChangePlanModalProps) {
  const [plans, setPlans] = useState<AdminPlanRead[]>([])
  const [loadingPlans, setLoadingPlans] = useState(true)
  const [targetPlanId, setTargetPlanId] = useState('')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await getAdminPlans({ skip: 0, limit: 100 })
        if (!cancelled) {
          setPlans(
            data.filter(
              (plan) => plan.is_active && plan.id !== subscription.plan_id,
            ),
          )
        }
      } catch (err) {
        if (!cancelled) setError(getFriendlyErrorMessage(err))
      } finally {
        if (!cancelled) setLoadingPlans(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [subscription.plan_id])

  const handleSubmit = async () => {
    if (!targetPlanId) {
      setError('Vui lòng chọn gói mới')
      return
    }
    if (reason.trim().length < 5) {
      setError('Lý do phải có ít nhất 5 ký tự')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await changeAdminSubscriptionPlan(subscription.id, {
        target_plan_id: targetPlanId,
        reason: reason.trim(),
      })
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
      ariaLabel="Đổi gói thuê bao"
      title={
        <span className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
          Đổi gói thuê bao
        </span>
      }
      description={`Người dùng: ${subscription.user_email ?? subscription.user_id}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            <X className="h-4 w-4 mr-2" aria-hidden="true" />
            Hủy
          </Button>
          <Button onClick={handleSubmit} isLoading={submitting} disabled={submitting}>
            Xác nhận đổi gói
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Gói hiện tại: <strong>{subscription.plan_name ?? '—'}</strong>. Việc đổi
          gói được thực hiện ngay và giữ nguyên hạn mức đã sử dụng.
        </p>

        <Select
          id="change-plan-target"
          label="Gói mới"
          value={targetPlanId}
          onChange={(event) => setTargetPlanId(event.target.value)}
          disabled={submitting || loadingPlans}
        >
          <option value="">
            {loadingPlans ? 'Đang tải danh sách gói...' : 'Chọn gói mới'}
          </option>
          {plans.map((plan) => (
            <option key={plan.id} value={plan.id}>
              {plan.name} — {plan.duration_days} ngày
            </option>
          ))}
        </Select>

        <div>
          <label htmlFor="change-plan-reason" className="block text-sm font-medium mb-1">
            Lý do đổi gói <span className="text-destructive">*</span>
          </label>
          <Textarea
            id="change-plan-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Nhập lý do đổi gói (tối thiểu 5 ký tự, tối đa 500 ký tự)..."
            rows={3}
            maxLength={500}
            disabled={submitting}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            {reason.length}/500 ký tự
          </p>
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
          >
            {error}
          </p>
        ) : null}
      </div>
    </Modal>
  )
}
