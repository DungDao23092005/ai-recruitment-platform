import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, CreditCard, RotateCcw, ShieldCheck } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { CompanySubscriptionCard } from '@/features/recruiter/components/CompanySubscriptionCard'
import { CompanyUsageHistoryTable } from '@/features/recruiter/components/CompanyUsageHistoryTable'
import { CompanyPaymentHistoryTable } from '@/features/recruiter/components/CompanyPaymentHistoryTable'
import {
  useCompanyPaymentHistory,
  useCompanyUsages,
} from '@/features/recruiter/hooks/useCompanyBilling'
import { useCompanySubscription } from '@/features/subscriptions/hooks/useCompanySubscription'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { getWorkspaceMembers } from '@/api/workspaces'
import type { WorkspaceMember } from '@/types/workspace'
import type {
  CompanyUsageQueryParams,
  SubscriptionUsageFeatureType,
} from '@/types/subscription'

const PAGE_SIZE = 10

const FEATURE_OPTIONS: Array<{
  value: SubscriptionUsageFeatureType
  label: string
}> = [
  { value: 'job_post', label: 'Tin tuyển dụng' },
  { value: 'candidate_search', label: 'Tìm kiếm ứng viên' },
  { value: 'recruiting_ai', label: 'AI tuyển dụng' },
  { value: 'ai_feature', label: 'AI tuyển dụng (cũ)' },
  { value: 'candidate_parse_resume', label: 'Phân tích CV' },
  { value: 'candidate_job_recommendations', label: 'Gợi ý việc làm' },
  { value: 'candidate_chat', label: 'Trò chuyện AI' },
]

function getVnDateString(date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function getDefaultRange(): { startDate: string; endDate: string } {
  const today = getVnDateString()
  const [year, month] = today.split('-')
  return { startDate: `${year}-${month}-01`, endDate: today }
}

function memberLabel(member: WorkspaceMember): string {
  return member.full_name || member.email
}

export function RecruiterBillingPage() {
  const {
    selectedCompanyId,
    selectedWorkspace,
    isLoading: isWorkspaceLoading,
  } = useWorkspace()
  const isAdmin = selectedWorkspace?.role === 'admin'
  const hasWorkspace = Boolean(selectedCompanyId)

  const defaultRange = useMemo(getDefaultRange, [])
  const [startDate, setStartDate] = useState(defaultRange.startDate)
  const [endDate, setEndDate] = useState(defaultRange.endDate)
  const [featureType, setFeatureType] = useState<
    SubscriptionUsageFeatureType | ''
  >('')
  const [userId, setUserId] = useState('')
  const [page, setPage] = useState(1)
  const [members, setMembers] = useState<WorkspaceMember[]>([])

  const {
    subscription,
    isLoading: isSubscriptionLoading,
    error: subscriptionError,
    refetch: refetchSubscription,
  } = useCompanySubscription(hasWorkspace)

  const usageParams = useMemo<CompanyUsageQueryParams>(
    () => ({
      page,
      page_size: PAGE_SIZE,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      feature_type: featureType || undefined,
      user_id: userId || undefined,
    }),
    [endDate, featureType, page, startDate, userId],
  )

  const {
    data: usageData,
    isLoading: isUsageLoading,
    error: usageError,
    refetch: refetchUsages,
  } = useCompanyUsages(usageParams, hasWorkspace)

  const {
    orders,
    isLoading: isPaymentsLoading,
    error: paymentsError,
    refetch: refetchPayments,
  } = useCompanyPaymentHistory(hasWorkspace)

  useEffect(() => {
    setPage(1)
    setUserId('')
  }, [selectedCompanyId])

  useEffect(() => {
    if (!hasWorkspace) {
      setMembers([])
      return
    }

    let active = true
    getWorkspaceMembers()
      .then((result) => {
        if (active) setMembers(result)
      })
      .catch(() => {
        if (active) setMembers([])
      })

    return () => {
      active = false
    }
  }, [hasWorkspace, selectedCompanyId])

  const handleStartDateChange = (value: string) => {
    setStartDate(value)
    setPage(1)
  }

  const handleEndDateChange = (value: string) => {
    setEndDate(value)
    setPage(1)
  }

  const handleFeatureChange = (value: string) => {
    setFeatureType(value as SubscriptionUsageFeatureType | '')
    setPage(1)
  }

  const handleUserChange = (value: string) => {
    setUserId(value)
    setPage(1)
  }

  const handleResetFilters = () => {
    const range = getDefaultRange()
    setStartDate(range.startDate)
    setEndDate(range.endDate)
    setFeatureType('')
    setUserId('')
    setPage(1)
  }

  if (isWorkspaceLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Nhà tuyển dụng"
          title="Gói & Thanh toán"
          description="Theo dõi gói dịch vụ, hạn mức và lịch sử sử dụng của công ty."
        />
        <div className="h-40 animate-pulse rounded-xl border border-border bg-muted/40" />
      </div>
    )
  }

  if (!hasWorkspace) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Nhà tuyển dụng"
          title="Gói & Thanh toán"
          description="Theo dõi gói dịch vụ, hạn mức và lịch sử sử dụng của công ty."
        />
        <EmptyState
          title="Chưa chọn công ty"
          description="Chọn một công ty làm việc để xem thông tin gói và thanh toán."
        />
      </div>
    )
  }

  const totalPages = usageData?.total_pages ?? 0

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={selectedWorkspace?.company_name ?? 'Nhà tuyển dụng'}
        title="Gói & Thanh toán"
        description="Theo dõi gói dịch vụ, hạn mức và lịch sử sử dụng của công ty."
      />

      <CompanySubscriptionCard
        subscription={subscription}
        isLoading={isSubscriptionLoading}
        error={subscriptionError}
        onRetry={refetchSubscription}
        isAdmin={isAdmin}
      />

      <Card className="border-border/70">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-display text-lg font-semibold">
            <ShieldCheck className="h-5 w-5 text-primary" aria-hidden="true" />
            Quản lý gói dịch vụ
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isAdmin ? (
            <div className="flex flex-wrap gap-2">
              <Link to="/plans?audience=company">
                <Button>
                  <CreditCard className="h-4 w-4" aria-hidden="true" />
                  {subscription ? 'Gia hạn hoặc thay đổi gói' : 'Chọn gói dịch vụ'}
                </Button>
              </Link>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Chỉ Quản trị viên công ty (Workspace Admin) mới có quyền mua hoặc
              thay đổi gói dịch vụ.
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-display text-lg font-semibold">
            <CalendarDays className="h-5 w-5 text-primary" aria-hidden="true" />
            Bộ lọc lịch sử sử dụng
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Input
              type="date"
              name="usage-start-date"
              label="Từ ngày"
              value={startDate}
              onChange={(event) => handleStartDateChange(event.target.value)}
            />
            <Input
              type="date"
              name="usage-end-date"
              label="Đến ngày"
              value={endDate}
              onChange={(event) => handleEndDateChange(event.target.value)}
            />
            <Select
              name="usage-feature"
              label="Tính năng"
              value={featureType}
              onChange={(event) => handleFeatureChange(event.target.value)}
            >
              <option value="">Tất cả tính năng</option>
              {FEATURE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
            <Select
              name="usage-member"
              label="Thành viên"
              value={userId}
              onChange={(event) => handleUserChange(event.target.value)}
            >
              <option value="">Tất cả thành viên</option>
              {members.map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {memberLabel(member)}
                </option>
              ))}
            </Select>
          </div>
          <div className="mt-4 flex justify-end">
            <Button variant="outline" size="sm" onClick={handleResetFilters}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Đặt lại bộ lọc
            </Button>
          </div>
        </CardContent>
      </Card>

      <CompanyUsageHistoryTable
        items={usageData?.items ?? []}
        isLoading={isUsageLoading}
        error={usageError}
        onRetry={refetchUsages}
      />

      <div className="flex flex-col items-center justify-between gap-3 sm:flex-row">
        <p className="text-sm text-muted-foreground">
          {usageData
            ? `${usageData.total.toLocaleString('vi-VN')} lượt sử dụng`
            : 'Chưa có dữ liệu'}
        </p>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1 || isUsageLoading}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            Trước
          </Button>
          <span className="text-sm text-muted-foreground">
            Trang {totalPages === 0 ? 0 : page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={totalPages === 0 || page >= totalPages || isUsageLoading}
            onClick={() => setPage((current) => current + 1)}
          >
            Sau
          </Button>
        </div>
      </div>

      <CompanyPaymentHistoryTable
        orders={orders}
        isLoading={isPaymentsLoading}
        error={paymentsError}
        onRetry={refetchPayments}
      />
    </div>
  )
}

export default RecruiterBillingPage
