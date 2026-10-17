import { useLocation, useNavigate } from 'react-router-dom'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  SearchX,
  XCircle,
  type LucideIcon,
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/button'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { getPaymentStatus } from '@/api/payments'
import { cn } from '@/utils/cn'
import type { PaymentStatusResponse } from '@/types/payment'

type ResultState = 'loading' | 'success' | 'processing' | 'pending' | 'failed' | 'invalid' | 'error'
type StatusTone = 'success' | 'warning' | 'destructive' | 'neutral'

// Bounded client polling. The backend reconciles each status check with VNPAY
// QueryDr; these retries are only a UX affordance for a slow-clearing payment.
const MAX_POLL_ATTEMPTS = 5
const POLL_INTERVAL_MS = 3000

const ORDER_STATUS_LABELS: Record<string, string> = {
  paid: 'Đã thanh toán',
  pending: 'Đang xử lý',
  failed: 'Thất bại',
  cancelled: 'Đã hủy',
  expired: 'Hết hạn',
  refunded: 'Đã hoàn tiền',
}

const SUBSCRIPTION_STATUS_LABELS: Record<string, string> = {
  active: 'Đang hoạt động',
  pending: 'Chờ kích hoạt',
  cancelled: 'Đã hủy',
  expired: 'Hết hạn',
}

const TONE_STYLES: Record<
  StatusTone,
  { border: string; iconBg: string; iconText: string }
> = {
  success: {
    border: 'border-success/30',
    iconBg: 'bg-success/10',
    iconText: 'text-success',
  },
  warning: {
    border: 'border-warning/30',
    iconBg: 'bg-warning/10',
    iconText: 'text-warning',
  },
  destructive: {
    border: 'border-destructive/30',
    iconBg: 'bg-destructive/10',
    iconText: 'text-destructive',
  },
  neutral: {
    border: 'border-border',
    iconBg: 'bg-muted',
    iconText: 'text-muted-foreground',
  },
}

function formatCurrency(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return `${amount.toLocaleString('vi-VN')} ${currency}`
  }
}

function formatDateTime(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)
}

function formatDate(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState<'idle' | 'copied' | 'error'>('idle')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    },
    [],
  )

  const handleCopy = useCallback(async () => {
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
        throw new Error('clipboard unavailable')
      }
      await navigator.clipboard.writeText(value)
      setCopied('copied')
    } catch {
      setCopied('error')
    }
    if (timerRef.current !== null) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setCopied('idle'), 2000)
  }, [value])

  const ariaLabel =
    copied === 'copied'
      ? 'Đã sao chép'
      : copied === 'error'
        ? 'Không thể sao chép'
        : label

  return (
    <span className="inline-flex items-center gap-1">
      <button
        type="button"
        onClick={handleCopy}
        aria-label={ariaLabel}
        title={ariaLabel}
        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        {copied === 'copied' ? (
          <Check className="h-3.5 w-3.5 text-success" aria-hidden="true" />
        ) : (
          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
        )}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {copied === 'copied' ? 'Đã sao chép' : copied === 'error' ? 'Không thể sao chép' : ''}
      </span>
    </span>
  )
}

function ReceiptRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <dt className="shrink-0 text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-all text-sm font-medium text-foreground sm:text-right">
        {children}
      </dd>
    </div>
  )
}

function ReceiptSkeleton() {
  return (
    <div className="container py-10 sm:py-12">
      <div className="mx-auto w-full max-w-xl" role="status" aria-busy="true" aria-live="polite">
        <span className="sr-only">Đang kiểm tra trạng thái thanh toán...</span>
        <Card>
          <CardContent className="p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <Skeleton className="h-11 w-11 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-5 w-2/3 rounded" />
                <Skeleton className="h-4 w-1/2 rounded" />
              </div>
            </div>
            <div className="mt-6 space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <Skeleton className="h-4 w-24 rounded" />
                  <Skeleton className="h-4 w-32 rounded" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          Đang xác minh giao dịch với VNPAY...
        </p>
      </div>
    </div>
  )
}

interface StatusMeta {
  icon: LucideIcon
  tone: StatusTone
  title: string
  badgeLabel: string
  badgeVariant: BadgeProps['variant']
}

const STATUS_META: Record<Exclude<ResultState, 'loading'>, StatusMeta> = {
  success: {
    icon: CheckCircle2,
    tone: 'success',
    title: 'Thanh toán thành công',
    badgeLabel: 'Đã kích hoạt',
    badgeVariant: 'success',
  },
  processing: {
    icon: Clock,
    tone: 'warning',
    title: 'Đã nhận thanh toán, đang kích hoạt gói',
    badgeLabel: 'Chờ kích hoạt',
    badgeVariant: 'warning',
  },
  pending: {
    icon: Clock,
    tone: 'warning',
    title: 'Giao dịch đang được xử lý',
    badgeLabel: 'Đang xử lý',
    badgeVariant: 'warning',
  },
  failed: {
    icon: XCircle,
    tone: 'destructive',
    title: 'Thanh toán thất bại',
    badgeLabel: 'Thất bại',
    badgeVariant: 'destructive',
  },
  invalid: {
    icon: SearchX,
    tone: 'destructive',
    title: 'Không tìm thấy giao dịch',
    badgeLabel: 'Không hợp lệ',
    badgeVariant: 'destructive',
  },
  error: {
    icon: AlertTriangle,
    tone: 'destructive',
    title: 'Không thể kiểm tra trạng thái thanh toán',
    badgeLabel: 'Lỗi xác minh',
    badgeVariant: 'destructive',
  },
}

export function PaymentResultPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { currentUser, refreshCurrentUser } = useAuth()
  const authRefreshedRef = useRef(false)

  // Resolve the merchant reference (vnp_TxnRef). The VNPAY return flow forwards
  // it as `order_id`; accept `vnp_TxnRef` directly as a fallback. Query-string
  // `success` / `message` / `vnp_ResponseCode` values are NEVER trusted for the
  // outcome - only the authenticated backend reconciliation response decides.
  const urlParams = new URLSearchParams(location.search)
  const orderId = urlParams.get('order_id') || urlParams.get('vnp_TxnRef')

  const [state, setState] = useState<ResultState>(orderId ? 'loading' : 'invalid')
  const [response, setResponse] = useState<PaymentStatusResponse | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const refreshAuthOnce = useCallback(async () => {
    if (authRefreshedRef.current) return
    authRefreshedRef.current = true
    try {
      await refreshCurrentUser()
    } catch {
      // The verified payment outcome must survive an auth refresh failure.
    }
  }, [refreshCurrentUser])

  useEffect(() => {
    if (!orderId) {
      setState('invalid')
      return
    }

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0

    setState('loading')

    const run = async () => {
      try {
        const res = await getPaymentStatus(orderId)
        if (cancelled) return

        if (res.is_successful || res.payment_order.status === 'paid') {
          // A verified payment is NOT the same as a granted entitlement. Only
          // show success when the server confirms the subscription is active;
          // a paid order whose subscription never activated must surface the
          // pending-activation state instead of a false upgrade confirmation.
          if (res.is_activated) {
            await refreshAuthOnce()
            if (cancelled) return
            setResponse(res)
            setState('success')
            return
          }
          setResponse(res)
          setState('processing')
          return
        }

        if (res.payment_order.status === 'pending') {
          if (attempt < MAX_POLL_ATTEMPTS) {
            attempt += 1
            timer = setTimeout(run, POLL_INTERVAL_MS)
            return
          }
          setResponse(res)
          setState('pending')
          return
        }

        // Any other definitive order status (failed / cancelled / expired).
        setResponse(res)
        setState('failed')
      } catch (err) {
        if (cancelled) return

        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 404) {
          // Unknown order or one that belongs to another user.
          setResponse(null)
          setState('invalid')
          return
        }

        if (attempt < MAX_POLL_ATTEMPTS) {
          attempt += 1
          timer = setTimeout(run, POLL_INTERVAL_MS)
          return
        }
        setResponse(null)
        setState('error')
      }
    }

    void run()

    return () => {
      cancelled = true
      if (timer !== null) clearTimeout(timer)
    }
  }, [orderId, reloadKey, refreshAuthOnce])

  const handleRetry = useCallback(() => {
    authRefreshedRef.current = false
    // Clear the previous verified response so stale data can never be shown as
    // a freshly verified receipt while the retry is in flight.
    setResponse(null)
    setReloadKey((key) => key + 1)
  }, [])

  const handleGoBack = useCallback(() => {
    navigate('/plans', { replace: true })
  }, [navigate])

  const handleGoRecruiterPortal = useCallback(() => {
    navigate('/recruiter/portal', { replace: true })
  }, [navigate])

  if (state === 'loading') {
    return <ReceiptSkeleton />
  }

  const meta = STATUS_META[state]
  const tone = TONE_STYLES[meta.tone]
  const StatusIcon = meta.icon
  const isRecruiter = currentUser?.role === 'recruiter' || currentUser?.role === 'admin'

  const planName = response?.plan_name ?? null
  const amountLabel = response
    ? formatCurrency(response.payment_order.amount, response.payment_order.currency)
    : null
  const orderStatusLabel = response
    ? (ORDER_STATUS_LABELS[response.payment_order.status] ?? response.payment_order.status)
    : null
  const subscriptionStatusLabel = response?.subscription_status
    ? (SUBSCRIPTION_STATUS_LABELS[response.subscription_status] ?? response.subscription_status)
    : null
  const internalOrderId = response?.payment_order.internal_order_id ?? null
  const providerTransactionId = response?.transaction?.provider_transaction_id ?? null
  const paidAtLabel = formatDateTime(response?.payment_order.paid_at)
  const expiresAtLabel = formatDate(response?.subscription_expires_at)

  const showReceipt = state !== 'invalid' && state !== 'error' && response !== null
  const hasPrimaryAction =
    (state === 'success' && isRecruiter) ||
    state === 'processing' ||
    state === 'pending' ||
    state === 'error'

  let description: ReactNode = null
  if (state === 'success') {
    description = planName
      ? `Gói "${planName}" đã được kích hoạt thành công.`
      : 'Thanh toán của bạn đã được xác nhận và gói dịch vụ đã được kích hoạt.'
  } else if (state === 'processing') {
    description = (
      <span>
        Hệ thống đã ghi nhận giao dịch thanh toán của bạn, nhưng quyền lợi gói dịch vụ chưa được
        xác nhận kích hoạt. Vui lòng không thanh toán lại để tránh bị trừ tiền hai lần.
      </span>
    )
  } else if (state === 'pending') {
    description =
      'Thanh toán của bạn đang được xác minh với VNPAY. Quá trình này có thể mất vài phút; bạn có thể kiểm tra lại trạng thái.'
  } else if (state === 'failed') {
    description = response?.message || 'Giao dịch không thành công hoặc đã bị hủy.'
  } else if (state === 'invalid') {
    description = 'Mã đơn hàng không hợp lệ hoặc không thuộc tài khoản của bạn.'
  } else {
    description =
      'Vui lòng thử lại. Giao dịch của bạn có thể vẫn đang được xử lý; chúng tôi chưa thể xác minh trạng thái thanh toán.'
  }

  return (
    <div className="container py-10 sm:py-12">
      <div className="mx-auto w-full max-w-xl">
        <Card className={cn('overflow-hidden', tone.border)}>
          <CardContent className="p-6 sm:p-8">
            <div className="flex items-start gap-4" aria-live="polite">
              <span
                className={cn(
                  'flex h-11 w-11 shrink-0 items-center justify-center rounded-full',
                  tone.iconBg,
                  tone.iconText,
                )}
              >
                <StatusIcon className="h-6 w-6" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <h1 className="text-lg font-semibold tracking-tight text-foreground sm:text-xl">
                  {meta.title}
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">{description}</p>
              </div>
              <Badge variant={meta.badgeVariant} className="shrink-0">
                {meta.badgeLabel}
              </Badge>
            </div>

            {planName && state !== 'invalid' && state !== 'error' && (
              <p className="mt-5 text-base font-medium text-foreground">{planName}</p>
            )}

            {showReceipt && response && (
              <dl className="mt-5 divide-y divide-border border-t border-border">
                {amountLabel && <ReceiptRow label="Số tiền">{amountLabel}</ReceiptRow>}
                {orderStatusLabel && (
                  <ReceiptRow label="Trạng thái thanh toán">{orderStatusLabel}</ReceiptRow>
                )}
                {subscriptionStatusLabel && (
                  <ReceiptRow label="Trạng thái gói">{subscriptionStatusLabel}</ReceiptRow>
                )}
                {internalOrderId && (
                  <ReceiptRow label="Mã đơn hàng">
                    <span className="inline-flex items-center gap-1">
                      <span>{internalOrderId}</span>
                      <CopyButton value={internalOrderId} label="Sao chép mã đơn hàng" />
                    </span>
                  </ReceiptRow>
                )}
                {providerTransactionId && (
                  <ReceiptRow label="Mã giao dịch VNPAY">
                    <span className="inline-flex items-center gap-1">
                      <span>{providerTransactionId}</span>
                      <CopyButton
                        value={providerTransactionId}
                        label="Sao chép mã giao dịch VNPAY"
                      />
                    </span>
                  </ReceiptRow>
                )}
                {paidAtLabel && (
                  <ReceiptRow label="Thời gian thanh toán">{paidAtLabel}</ReceiptRow>
                )}
                {expiresAtLabel && <ReceiptRow label="Hiệu lực đến">{expiresAtLabel}</ReceiptRow>}
              </dl>
            )}

            <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
              {state === 'success' && isRecruiter && (
                <Button onClick={handleGoRecruiterPortal}>Bắt đầu tuyển dụng</Button>
              )}
              {(state === 'processing' || state === 'pending') && (
                <Button onClick={handleRetry}>Kiểm tra lại</Button>
              )}
              {state === 'error' && <Button onClick={handleRetry}>Thử lại</Button>}
              <Button
                variant={hasPrimaryAction ? 'outline' : 'default'}
                onClick={handleGoBack}
              >
                Quay lại gói dịch vụ
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

PaymentResultPage.displayName = 'PaymentResultPage'

export default PaymentResultPage
