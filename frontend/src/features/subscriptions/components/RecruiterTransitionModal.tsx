import * as React from 'react'
import { ArrowRight, Info, ShieldCheck, UserRoundX } from 'lucide-react'
import { Modal } from '@/components/ui/modal'
import { Button } from '@/components/ui/button'
import { formatPlanDuration, formatPlanPrice } from './PlanCard'
import type { RecruitmentPlanRead } from '@/types/subscription'

export interface RecruiterTransitionModalProps {
  plan: RecruitmentPlanRead
  onClose: () => void
  onConfirm: () => void
}

export function RecruiterTransitionModal({
  plan,
  onClose,
  onConfirm,
}: RecruiterTransitionModalProps) {
  const [acknowledged, setAcknowledged] = React.useState(false)
  const checkboxId = React.useId()
  const contentRef = React.useRef<HTMLDivElement>(null)
  const previouslyFocusedRef = React.useRef<HTMLElement | null>(null)

  React.useEffect(() => {
    const previouslyFocused = document.activeElement
    if (previouslyFocused instanceof HTMLElement) {
      previouslyFocusedRef.current = previouslyFocused
    }
    contentRef.current?.focus()

    return () => {
      previouslyFocusedRef.current?.focus()
    }
  }, [])

  const quotas: Array<{ label: string; value: string }> = [
    { label: 'Bài đăng tin', value: String(plan.max_job_posts) },
  ]

  if (
    plan.max_candidate_searches !== null &&
    plan.max_candidate_searches !== undefined
  ) {
    quotas.push({
      label: 'Tìm kiếm ứng viên',
      value: String(plan.max_candidate_searches),
    })
  }

  if (plan.max_ai_features !== null && plan.max_ai_features !== undefined) {
    quotas.push({ label: 'Tính năng AI', value: String(plan.max_ai_features) })
  }

  return (
    <Modal
      size="md"
      title="Bạn muốn trở thành nhà tuyển dụng?"
      description="Xác nhận gói để tiếp tục tới bước thanh toán."
      ariaLabel="Bạn muốn trở thành nhà tuyển dụng?"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Hủy
          </Button>
          <Button
            type="button"
            onClick={onConfirm}
            disabled={!acknowledged}
          >
            Tiếp tục tới thanh toán
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </>
      }
    >
      <div ref={contentRef} tabIndex={-1} className="space-y-5 outline-none">
        <div className="rounded-xl border bg-muted/30 p-4">
          <p className="text-sm font-semibold text-foreground">{plan.name}</p>
          <p className="mt-1 flex items-baseline gap-1.5">
            <span className="font-display text-2xl font-bold tracking-tight text-foreground">
              {formatPlanPrice(plan.price, plan.currency)}
            </span>
            <span className="text-sm text-muted-foreground">
              / {formatPlanDuration(plan.duration_days)}
            </span>
          </p>
          <dl className="mt-3 grid grid-cols-1 gap-3 border-t border-border pt-3 sm:grid-cols-3">
            {quotas.map((quota) => (
              <div key={quota.label}>
                <dt className="text-xs text-muted-foreground">{quota.label}</dt>
                <dd className="text-sm font-semibold text-foreground">
                  {quota.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <section aria-labelledby={`${checkboxId}-changes`}>
          <h3
            id={`${checkboxId}-changes`}
            className="text-sm font-semibold text-foreground"
          >
            Điều gì sẽ thay đổi
          </h3>
          <ul className="mt-2 space-y-2.5 text-sm text-muted-foreground">
            <li className="flex gap-2.5">
              <ShieldCheck
                className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                aria-hidden="true"
              />
              <span>
                Tài khoản của bạn được chuyển từ{' '}
                <strong className="font-semibold text-foreground">Ứng viên</strong> sang{' '}
                <strong className="font-semibold text-foreground">
                  Nhà tuyển dụng
                </strong>{' '}
                sau khi hệ thống xác minh thanh toán thành công.
              </span>
            </li>
            <li className="flex gap-2.5">
              <UserRoundX
                className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
                aria-hidden="true"
              />
              <span>
                Các tính năng chỉ dành riêng cho ứng viên sẽ không còn truy cập
                được sau khi chuyển đổi.
              </span>
            </li>
            <li className="flex gap-2.5">
              <ShieldCheck
                className="mt-0.5 h-4 w-4 shrink-0 text-success"
                aria-hidden="true"
              />
              <span>
                Hồ sơ, CV và lịch sử ứng tuyển của bạn vẫn được lưu giữ.
              </span>
            </li>
          </ul>
        </section>

        <p className="flex gap-2.5 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-foreground">
          <Info
            className="mt-0.5 h-4 w-4 shrink-0 text-warning"
            aria-hidden="true"
          />
          <span>
            Mở cửa sổ này không thay đổi vai trò của bạn. Vai trò chỉ thay đổi
            sau khi hệ thống xác minh thanh toán thành công.
          </span>
        </p>

        <div className="flex items-start gap-2.5">
          <input
            id={checkboxId}
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-input text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          />
          <label
            htmlFor={checkboxId}
            className="cursor-pointer text-sm text-foreground"
          >
            Tôi hiểu rằng tài khoản của tôi sẽ chuyển sang vai trò Nhà tuyển
            dụng sau khi thanh toán thành công và tôi có thể mất các tính năng
            dành riêng cho ứng viên.
          </label>
        </div>
      </div>
    </Modal>
  )
}

RecruiterTransitionModal.displayName = 'RecruiterTransitionModal'

export default RecruiterTransitionModal
