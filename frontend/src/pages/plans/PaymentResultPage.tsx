import { useLocation, useNavigate } from 'react-router-dom'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/button'
import { getPaymentStatus } from '@/api/payments'

type ResultState = 'loading' | 'success' | 'processing' | 'failed' | 'pending' | 'invalid' | 'error'

// Bounded client polling. The backend reconciles each status check with VNPAY
// QueryDr; these retries are only a UX affordance for a slow-clearing payment.
const MAX_POLL_ATTEMPTS = 5
const POLL_INTERVAL_MS = 3000

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
  const [paymentMessage, setPaymentMessage] = useState('')
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
            setPaymentMessage(res.message)
            setState('success')
            return
          }
          setPaymentMessage(res.message)
          setState('processing')
          return
        }

        if (res.payment_order.status === 'pending') {
          setPaymentMessage(res.message)
          if (attempt < MAX_POLL_ATTEMPTS) {
            attempt += 1
            timer = setTimeout(run, POLL_INTERVAL_MS)
            return
          }
          setState('pending')
          return
        }

        // Any other definitive order status (failed / cancelled / expired).
        setPaymentMessage(res.message)
        setState('failed')
      } catch (err) {
        if (cancelled) return

        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 404) {
          // Unknown order or one that belongs to another user.
          setState('invalid')
          return
        }

        if (attempt < MAX_POLL_ATTEMPTS) {
          attempt += 1
          timer = setTimeout(run, POLL_INTERVAL_MS)
          return
        }
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
    setPaymentMessage('')
    setReloadKey((key) => key + 1)
  }, [])

  const handleGoBack = useCallback(() => {
    navigate('/plans', { replace: true })
  }, [navigate])

  const handleGoRecruiterPortal = useCallback(() => {
    navigate('/recruiter/portal', { replace: true })
  }, [navigate])

  const isRecruiter = currentUser?.role === 'recruiter'

  return (
    <div className="container py-10 sm:py-12">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          {state === 'loading' && (
            <div className="flex items-center justify-center h-96 text-muted-foreground">
              Đang kiểm tra trạng thái thanh toán...
            </div>
          )}

          {state === 'pending' && (
            <div className="p-6 rounded-lg mb-6 bg-yellow-50 border-yellow-200">
              <h3 className="font-semibold text-yellow-700 mb-2">
                Giao dịch đang được xử lý
              </h3>
              <p className="text-yellow-700 mb-4">
                {paymentMessage || 'Thanh toán của bạn đang được xác nhận.'}
              </p>
              <div className="flex gap-3">
                <Button onClick={handleRetry}>Kiểm tra lại</Button>
                <Button variant="outline" onClick={handleGoBack}>
                  Quay lại gói dịch vụ
                </Button>
              </div>
            </div>
          )}

          {state === 'processing' && (
            <div className="p-6 rounded-lg mb-6 bg-yellow-50 border-yellow-200">
              <h3 className="font-semibold text-yellow-700 mb-2">
                Đã nhận thanh toán, đang kích hoạt gói
              </h3>
              <p className="text-yellow-700 mb-4">
                Chúng tôi đã ghi nhận thanh toán của bạn. Gói dịch vụ đang được kích hoạt, vui
                lòng kiểm tra lại sau ít phút hoặc liên hệ hỗ trợ nếu tình trạng kéo dài.
              </p>
              <div className="flex gap-3">
                <Button onClick={handleRetry}>Kiểm tra lại</Button>
                <Button variant="outline" onClick={handleGoBack}>
                  Quay lại gói dịch vụ
                </Button>
              </div>
            </div>
          )}

          {state === 'invalid' && (
            <div className="p-6 rounded-lg mb-6 bg-red-50 border-red-200">
              <h3 className="font-semibold text-red-600 mb-2">
                Không tìm thấy giao dịch
              </h3>
              <p className="text-red-600 mb-4">
                Mã đơn hàng không hợp lệ hoặc không thuộc tài khoản của bạn.
              </p>
              <Button onClick={handleGoBack}>Quay lại gói dịch vụ</Button>
            </div>
          )}

          {state === 'error' && (
            <div className="p-6 rounded-lg mb-6 bg-red-50 border-red-200">
              <h3 className="font-semibold text-red-600 mb-2">
                Không thể kiểm tra trạng thái thanh toán
              </h3>
              <p className="text-red-600 mb-4">
                Vui lòng thử lại. Giao dịch của bạn có thể vẫn đang được xử lý.
              </p>
              <div className="flex gap-3">
                <Button onClick={handleRetry}>Thử lại</Button>
                <Button variant="outline" onClick={handleGoBack}>
                  Quay lại gói dịch vụ
                </Button>
              </div>
            </div>
          )}

          {state === 'success' && (
            <div className="p-6 rounded-lg mb-6 bg-green-50 border-green-200">
              {isRecruiter ? (
                <>
                  <h3 className="font-semibold text-green-600 mb-2">
                    Bạn đã được nâng cấp lên Nhà tuyển dụng thành công
                  </h3>
                  <p className="text-green-600 mb-4">
                    Bắt đầu quản lý công ty và đăng tin tuyển dụng ngay.
                  </p>
                  <div className="flex gap-3">
                    <Button onClick={handleGoRecruiterPortal}>
                      Bắt đầu tuyển dụng
                    </Button>
                    <Button variant="outline" onClick={handleGoBack}>
                      Quay lại gói dịch vụ
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <h3 className="font-semibold text-green-600 mb-2">
                    Thanh toán thành công
                  </h3>
                  <p className="text-green-600 mb-4">
                    {paymentMessage || 'Thanh toán thành công'}
                  </p>
                  <Button onClick={handleGoBack}>Quay lại gói dịch vụ</Button>
                </>
              )}
            </div>
          )}

          {state === 'failed' && (
            <div className="p-6 rounded-lg mb-6 bg-red-50 border-red-200">
              <h3 className="font-semibold text-red-600 mb-2">
                Thanh toán thất bại
              </h3>
              <p className="text-red-600 mb-4">
                {paymentMessage || 'Giao dịch không thành công.'}
              </p>
              <Button onClick={handleGoBack}>Quay lại gói dịch vụ</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

PaymentResultPage.displayName = 'PaymentResultPage'

export default PaymentResultPage
