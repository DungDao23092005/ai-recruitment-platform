import * as React from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ArrowLeft, CreditCard, Shield, Package } from 'lucide-react'
import { getPlan } from '@/api/plans'
import { createVNPayPayment } from '@/api/payments'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Skeleton } from '@/components/ui/skeleton'

interface PlanInfo {
  id: string
  name: string
  description: string
  price: number
  currency: string
  duration_days: number
  max_job_posts: number
  max_candidate_searches: number | null
  max_ai_features: number | null
  features?: string[]
}

function formatPrice(price: number, currency: string): string {
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(price)
}

function formatDuration(days: number): string {
  if (days >= 365) {
    const years = Math.floor(days / 365)
    return `${years} năm`
  }
  if (days >= 30) {
    const months = Math.floor(days / 30)
    return `${months} tháng`
  }
  return `${days} ngày`
}

export function CheckoutPage() {
  const { planId } = useParams<{ planId: string }>()
  const navigate = useNavigate()

  const [plan, setPlan] = React.useState<PlanInfo | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  React.useEffect(() => {
    if (!planId) {
      navigate('/plans')
      return
    }

    let mounted = true

    const fetchPlan = async () => {
      try {
        const data = await getPlan(planId)
        if (mounted) {
          setPlan({
            id: data.id,
            name: data.name,
            description: data.description || '',
            price: data.price,
            currency: data.currency,
            duration_days: data.duration_days,
            max_job_posts: data.max_job_posts,
            max_candidate_searches: data.max_candidate_searches ?? null,
            max_ai_features: data.max_ai_features ?? null,
            features: data.features,
          })
          setError(null)
        }
      } catch (err) {
        if (mounted) {
          setError('Không thể tải thông tin gói. Vui lòng thử lại.')
        }
      } finally {
        if (mounted) {
          setIsLoading(false)
        }
      }
    }

    fetchPlan()

    return () => {
      mounted = false
    }
  }, [planId, navigate])

  if (!planId) {
    navigate('/plans')
    return null
  }

  const handlePay = async (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault()

    if (isSubmitting) return

    setIsSubmitting(true)
    setError(null)

    try {
      const res = await createVNPayPayment(plan!.id)
      window.location.href = res.payment_url
    } catch (err) {
      const axiosErr = err as {
        response?: { status?: number; data?: { detail?: string } }
        message?: string
      }
      const status = axiosErr?.response?.status
      const serverDetail = axiosErr?.response?.data?.detail

      if (status === 409) {
        setError(
          serverDetail ||
            'Bạn đang có gói đăng tin đang hoạt động. Hệ thống chỉ hỗ trợ nâng cấp lên gói có giá cao hơn gói hiện tại. Vui lòng chọn gói cao hơn hoặc liên hệ hỗ trợ.'
        )
      } else if (serverDetail) {
        setError(serverDetail)
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Có lỗi xảy ra khi tạo thanh toán. Vui lòng thử lại sau.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleGoBack = () => {
    navigate('/plans')
  }

  const renderSkeleton = () => (
    <div className="container py-10 sm:py-12">
      <div className="max-w-7xl mx-auto" data-testid="skeleton">
        <Skeleton className="h-10 w-1/3 mb-8 rounded" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-64 w-full rounded-xl" />
            <Skeleton className="h-40 w-full rounded-xl" />
          </div>
          <div className="space-y-6">
            <Skeleton className="h-48 w-full rounded-xl" />
            <Skeleton className="h-20 w-full rounded-lg" />
          </div>
        </div>
      </div>
    </div>
  )

  if (isLoading) {
    return renderSkeleton()
  }

  if (error && !plan) {
    return (
      <div className="container py-10 sm:py-12">
        <div className="max-w-7xl mx-auto text-center">
          <ErrorBanner message={error} onRetry={handleGoBack} />
          <Button variant="outline" onClick={handleGoBack} className="mt-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Quay lại danh sách gói
          </Button>
        </div>
      </div>
    )
  }

  if (!plan) {
    return (
      <div className="container py-10 sm:py-12">
        <div className="max-w-7xl mx-auto text-center">
          <div className="py-12">
            <Package className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h2 className="text-xl font-semibold mb-2">Không tìm thấy gói</h2>
            <p className="text-muted-foreground mb-6">
              Gói này không tồn tại hoặc không còn khả dụng.
            </p>
            <Button variant="outline" onClick={handleGoBack}>
              <ArrowLeft className="h-4 w-4 mr-2" />
              Quay lại danh sách gói
            </Button>
          </div>
        </div>
      </div>
    )
  }

  const hasMaxCandidateSearches = plan.max_candidate_searches !== null && plan.max_candidate_searches !== undefined && plan.max_candidate_searches > 0
  const hasMaxAiFeatures = plan.max_ai_features !== null && plan.max_ai_features !== undefined && plan.max_ai_features > 0

  return (
    <div className="container py-10 sm:py-12">
      <div className="max-w-7xl mx-auto">
        {/* Back Button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={handleGoBack}
          className="mb-6"
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          Quay lại danh sách gói
        </Button>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Content - Plan Details */}
          <div className="lg:col-span-2 space-y-6">
            {/* Plan Info Card */}
            <div className="border rounded-xl p-6">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div className="flex-1">
                  <h2 className="text-2xl font-bold text-foreground">
                    {plan.name}
                  </h2>
                </div>
                <div className="flex-shrink-0 text-right">
                  <div className="text-3xl font-bold text-foreground">
                    {formatPrice(plan.price, plan.currency)}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    / {formatDuration(plan.duration_days)}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-4 border-t">
                <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                  <div className="p-2 rounded-lg bg-primary/10 text-primary">
                    <Package className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Số bài đăng</p>
                    <p className="font-semibold">{plan.max_job_posts} bài</p>
                  </div>
                </div>

                {hasMaxCandidateSearches && (
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                    <div className="p-2 rounded-lg bg-blue-100 text-blue-600">
                      <CreditCard className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Tìm kiếm ứng viên</p>
                      <p className="font-semibold">{plan.max_candidate_searches} lần</p>
                    </div>
                  </div>
                )}

                {hasMaxAiFeatures && (
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                    <div className="p-2 rounded-lg bg-purple-100 text-purple-600">
                      <Shield className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Tính năng AI</p>
                      <p className="font-semibold">{plan.max_ai_features} lần</p>
                    </div>
                  </div>
                )}
              </div>

              {plan.features && plan.features.length > 0 && (
                <div className="mt-6 pt-6 border-t">
                  <h3 className="text-sm font-semibold text-foreground mb-3">
                    Đặc điểm nổi bật
                  </h3>
                  <ul className="space-y-2 text-sm text-muted-foreground">
                    {plan.features.map((feature, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="text-primary mt-0.5">•</span>
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Confirmation */}
            <div className="border rounded-xl p-6 bg-muted/30">
              <p className="text-sm text-muted-foreground">
                Bạn sắp thanh toán cho gói <strong className="text-foreground">{plan.name}</strong>
                với giá <strong className="text-foreground">{formatPrice(plan.price, plan.currency)}</strong>
                cho thời hạn <strong className="text-foreground">{formatDuration(plan.duration_days)}</strong>.
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                Giao dịch sẽ được chuyển sang cổng thanh toán <strong className="text-foreground">VNPAY</strong>
                để hoàn tất. Sau khi thanh toán thành công, gói sẽ được kích hoạt ngay lập tức.
              </p>
            </div>
          </div>

          {/* Sidebar - Order Summary & Payment */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 space-y-6">
              {/* Order Summary */}
              <div className="border rounded-xl p-6">
                <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
                  <CreditCard className="h-5 w-5 text-primary" />
                  Tóm tắt đơn hàng
                </h3>

                <dl className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">Gói {plan.name}</dt>
                    <dd className="font-medium text-foreground">{formatPrice(plan.price, plan.currency)}</dd>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <dt>Thời hạn</dt>
                    <dd>{formatDuration(plan.duration_days)}</dd>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <dt>Số bài đăng</dt>
                    <dd>{plan.max_job_posts} bài</dd>
                  </div>
                  {hasMaxCandidateSearches && (
                    <div className="flex justify-between text-muted-foreground">
                      <dt>Tìm kiếm ứng viên</dt>
                      <dd>{plan.max_candidate_searches} lần</dd>
                    </div>
                  )}
                  {hasMaxAiFeatures && (
                    <div className="flex justify-between text-muted-foreground">
                      <dt>Tính năng AI</dt>
                      <dd>{plan.max_ai_features} lần</dd>
                    </div>
                  )}
                  <div className="border-t pt-3 flex justify-between text-base font-semibold">
                    <dt>Tổng thanh toán</dt>
                    <dd className="text-foreground">{formatPrice(plan.price, plan.currency)}</dd>
                  </div>
                </dl>


              </div>

              {/* Payment CTA */}
              <div className="border rounded-xl p-6 bg-muted/30">
                <Button
                  onClick={handlePay}
                  disabled={isSubmitting}
                  size="lg"
                  className="w-full"
                >
                  {isSubmitting ? (
                    <>
                      <svg
                        className="mr-2 h-5 w-5 animate-spin"
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                      </svg>
                      Đang tạo thanh toán...
                    </>
                  ) : (
                    <>
                      <CreditCard className="h-5 w-5 mr-2" />
                      Thanh toán với VNPAY
                    </>
                  )}
                </Button>

                {!isSubmitting && (
                  <p className="mt-3 text-center text-xs text-muted-foreground">
                    Bạn sẽ được chuyển hướng đến trang thanh toán VNPAY.
                  </p>
                )}

                {error && (
                  <ErrorBanner
                    message={error}
                    className="mt-4"
                  />
                )}
              </div>

              {/* Security Notice */}
              <div className="flex items-start gap-2 p-4 rounded-lg bg-blue-50 border border-blue-100">
                <Shield className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
                <div className="text-xs text-blue-700">
                  <p className="font-medium">Giao dịch được xử lý và bảo mật qua cổng thanh toán VNPAY.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

CheckoutPage.displayName = 'CheckoutPage'

export default CheckoutPage
