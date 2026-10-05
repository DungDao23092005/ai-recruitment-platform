import { useLocation, useNavigate } from 'react-router-dom'
import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { getPaymentStatus } from '@/api/payments'

export function PaymentResultPage() {
  const location = useLocation()
  const navigate = useNavigate()

  // Parse order_id from query parameters
  const urlParams = new URLSearchParams(location.search)
  const orderId = urlParams.get('order_id')

  const [isSuccessful, setIsSuccessful] = useState<boolean | null>(null)
  const [paymentMessage, setPaymentMessage] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)
  const [retryCount, setRetryCount] = useState(0)

  // Fetch payment status from backend
  const loadStatus = useCallback(async (internalOrderId: string) => {
    try {
      const res = await getPaymentStatus(internalOrderId)
      setIsSuccessful(res.is_successful)
      setPaymentMessage(res.message)

      // Determine pending vs definitive using payment_order.status per backend contract
      if (res.payment_order.status === 'pending') {
        startPolling(internalOrderId)
      } else {
        setIsLoading(false)
      }
    } catch (err) {
      setIsSuccessful(false)
      setPaymentMessage('Không thể kiểm tra trạng thái thanh toán')
      setIsLoading(false)
    }
  }, [])

  // Start polling for pending status
  const startPolling = useCallback(
    (internalOrderId: string) => {
      if (retryCount >= 5) {
        setIsLoading(false)
        return
      }

      ;(async () => {
        try {
          const res = await getPaymentStatus(internalOrderId)
          setIsSuccessful(res.is_successful)
          setPaymentMessage(res.message)

          // Check payment_order.status for definitive state
          if (res.payment_order.status === 'success') {
            setIsLoading(false)
          } else if (res.payment_order.status === 'failed') {
            setIsLoading(false)
          } else if (res.payment_order.status === 'pending') {
            // Still pending, retry after 3 seconds
            setRetryCount(retryCount + 1)
            setTimeout(() => startPolling(internalOrderId), 3000)
          } else {
            // Unknown status, stop polling
            setIsLoading(false)
          }
        } catch (err) {
          // Polling error, retry
          setTimeout(() => startPolling(internalOrderId), 3000)
        }
      })()
    },
    [retryCount, getPaymentStatus]
  )

  // Effect: initial load
  useEffect(() => {
    if (!orderId) {
      setIsLoading(false)
      window.alert('Thiếu order_id')
      return
    }

    setIsLoading(true)
    loadStatus(orderId)
  }, [orderId, loadStatus])

  // Effect: cleanup on unmount
  useEffect(() => {
    return () => {
      // No explicit timer cleanup needed as each poll is bounded by retryCount >= 5
    }
  }, [])

  // Navigation CTAs
  const handleGoBack = useCallback(() => {
    navigate('/plans', { replace: true })
  }, [navigate])

  return (
    <div className="container py-10 sm:py-12">
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          {isLoading && orderId && (
            <div className="flex items-center justify-center h-96 text-muted-foreground">
              Đang kiểm tra trạng thái thanh toán...
            </div>
          )}

          {isLoading && !orderId && (
            <div className="alert alert-error">
              Thiếu order_id
            </div>
          )}

          {!isLoading && orderId && isSuccessful !== null && (
            <div className="p-6 rounded-lg mb-6">
              {isSuccessful && (
                <div className="bg-green-50 border-green-200">
                  <h3 className="font-semibold text-green-600 mb-2">Thanh toán thành công</h3>
                  <p className="text-green-600">{paymentMessage}</p>
                  <Button onClick={handleGoBack}>Quay lại gói dịch vụ</Button>
                </div>
              )}

              {!isSuccessful && (
                <div className="bg-red-50 border-red-200">
                  <h3 className="font-semibold text-red-600 mb-2">Thanh toán thất bại</h3>
                  <p className="text-red-600">{paymentMessage}</p>
                  <Button onClick={handleGoBack}>Quay lại gói dịch vụ</Button>
                </div>
              )}
            </div>
          )}

          {!isLoading && !orderId && isSuccessful === null && (
            <div className="alert alert-error">
              Thiếu order_id
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

PaymentResultPage.displayName = 'PaymentResultPage'

export default PaymentResultPage