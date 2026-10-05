import * as React from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { getPlan } from '@/api/plans'
import { createVNPayPayment } from '@/api/payments'
import { cn } from '@/utils/cn'

export interface CheckoutPlanInfo {
  id: string
  name: string
  description: string
  price: number
  currency: string
  duration_days: number
  max_job_posts: number
  features?: string[]
}

export function CheckoutPage() {
  const { planId } = useParams<{ planId: string }>()
  const navigate = useNavigate()

  const [plan, setPlan] = React.useState<CheckoutPlanInfo | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  // Fetch plan when planId changes
  React.useEffect(() => {
    if (!planId) return

    ;(async () => {
      try {
        const data = await getPlan(planId)
        setPlan({
          id: data.id,
          name: data.name,
          description: data.description,
          price: data.price,
          currency: data.currency,
          duration_days: data.duration_days,
          max_job_posts: data.max_job_posts,
          features: data.features,
        })
      } catch (err) {
        window.alert('Không thể tải thông tin gói')
        navigate('/plans')
      }
    })()
  }, [planId, getPlan, navigate])

  if (!planId) {
    navigate('/plans')
    return null
  }

  if (!plan) {
    return (
      <div className="container py-10 sm:py-12">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-center h-96 text-muted-foreground">
            Gói không tìm thấy hoặc không còn khả dụng
          </div>
          <Button
            variant="outline"
            onClick={() => navigate('/plans')}
          >
            Quay lại gói dịch vụ
          </Button>
        </div>
      </div>
    )
  }

  const handlePay = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()

    setIsSubmitting(true)

    try {
      const res = await createVNPayPayment(plan.id)
      window.location.href = res.payment_url
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Có lỗi xảy ra khi tạo thanh toán'
      window.alert('Lỗi thanh toán: ' + message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="container py-10 sm:py-12">
      <div className="max-w-7xl mx-auto">

        {/* Plan Info Card */}
        <div className={cn('border rounded-lg p-6 mb-8', { 'border-primary': plan })} >
          <h2 className="font-semibold leading-none tracking-tick mb-4">Gói {plan.name}</h2>
          <p className="text-muted-foreground line-clamp-3">{plan.description}</p>

          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <span className="font-medium">Giá</span>
              <p className="mt-1 text-lg font-medium">
                {plan.price.toLocaleString()} {plan.currency}
              </p>
            </div>
            <div>
              <span className="font-medium">Thời gian</span>
              <p className="mt-1">
                {plan.duration_days} ngày
              </p>
            </div>
            <div>
              <span className="font-medium">Số bài đăng</span>
              <p className="mt-1">
                {plan.max_job_posts} bài
              </p>
            </div>
          </div>

          {plan.features && plan.features.length > 0 && (
            <div className="mt-4">
              <span className="font-semibold text-sm">Đặc điểm nổi bật:</span>
              <div className="mt-2">
                {plan.features.map((feature, idx) => (
                  <span key={idx} className="block mb-1">
                    • {feature}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Confirmation and Payment UI */}
        <div>
          {/* Confirmation */}
          {plan && (
            <p className="text-sm text-muted-foreground mb-4">
              Bạn sẽ được xác nhận quyền đăng {plan.max_job_posts} công việc trong {plan.duration_days} ngày.
            </p>
          )}

          {/* Payment CTA */}
          <Button
            disabled={isSubmitting}
            variant="outline"
            size="lg"
            className="w-full mt-6"
            onClick={handlePay}
          >
            {isSubmitting
              ? 'Đang tạo thanh toán...'
              : 'Thanh toán với VNPAY'}
          </Button>

          {!isSubmitting && (
            <p className="mt-2 text-xs text-muted-foreground">
              Nhấp lại nếu thanh toán không chuyển hướng.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

CheckoutPage.displayName = 'CheckoutPage'

export default CheckoutPage