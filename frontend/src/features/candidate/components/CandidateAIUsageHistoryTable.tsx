import { useMemo, useState } from 'react'
import { History } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useCandidateUsageHistory } from '@/features/candidate/hooks/useCandidateUsageHistory'
import type {
  CandidateUsageQueryParams,
  SubscriptionUsageFeatureType,
  SubscriptionUsageStatus,
} from '@/types/subscription'

export interface CandidateAIUsageHistoryTableProps {
  enabled?: boolean
}

const PAGE_SIZE = 10

const STATUS_VARIANTS: Record<
  SubscriptionUsageStatus,
  'success' | 'warning' | 'destructive'
> = {
  reserved: 'warning',
  completed: 'success',
  failed: 'destructive',
}

const FEATURE_OPTIONS: Array<{
  value: SubscriptionUsageFeatureType
  label: string
}> = [
  { value: 'candidate_parse_resume', label: 'Phân tích CV' },
  { value: 'candidate_job_recommendations', label: 'Gợi ý việc làm' },
  { value: 'candidate_chat', label: 'Trò chuyện AI' },
]

const STATUS_OPTIONS: Array<{
  value: SubscriptionUsageStatus
  label: string
}> = [
  { value: 'reserved', label: 'Đang xử lý' },
  { value: 'completed', label: 'Hoàn tất' },
  { value: 'failed', label: 'Thất bại' },
]

function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Không hợp lệ'
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)
}

export function CandidateAIUsageHistoryTable({
  enabled = true,
}: CandidateAIUsageHistoryTableProps) {
  const [page, setPage] = useState(1)
  const [featureType, setFeatureType] = useState<
    SubscriptionUsageFeatureType | ''
  >('')
  const [usageStatus, setUsageStatus] = useState<SubscriptionUsageStatus | ''>(
    '',
  )
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const params = useMemo<CandidateUsageQueryParams>(
    () => ({
      page,
      page_size: PAGE_SIZE,
      ...(featureType ? { feature_type: featureType } : {}),
      ...(usageStatus ? { status: usageStatus } : {}),
      ...(startDate ? { start_date: startDate } : {}),
      ...(endDate ? { end_date: endDate } : {}),
    }),
    [page, featureType, usageStatus, startDate, endDate],
  )

  const { data, isLoading, error, refetch } = useCandidateUsageHistory(
    params,
    enabled,
  )

  const resetFilters = () => {
    setFeatureType('')
    setUsageStatus('')
    setStartDate('')
    setEndDate('')
    setPage(1)
  }

  const totalPages = data?.total_pages ?? 0

  return (
    <Card className="border-border/70">
      <CardHeader className="gap-4">
        <CardTitle className="font-display text-lg font-semibold">
          Lịch sử sử dụng AI
        </CardTitle>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Select
            aria-label="Lọc theo tính năng"
            value={featureType}
            onChange={(event) => {
              setFeatureType(
                event.target.value as SubscriptionUsageFeatureType | '',
              )
              setPage(1)
            }}
          >
            <option value="">Tất cả tính năng</option>
            {FEATURE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Lọc theo trạng thái"
            value={usageStatus}
            onChange={(event) => {
              setUsageStatus(
                event.target.value as SubscriptionUsageStatus | '',
              )
              setPage(1)
            }}
          >
            <option value="">Tất cả trạng thái</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Input
            type="date"
            aria-label="Từ ngày"
            value={startDate}
            onChange={(event) => {
              setStartDate(event.target.value)
              setPage(1)
            }}
          />
          <Input
            type="date"
            aria-label="Đến ngày"
            value={endDate}
            onChange={(event) => {
              setEndDate(event.target.value)
              setPage(1)
            }}
          />
        </div>
        <div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={resetFilters}
          >
            Đặt lại bộ lọc
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <ErrorBanner message={error} onRetry={refetch} />
        ) : isLoading ? (
          <div className="space-y-3" data-testid="candidate-usage-loading">
            {[1, 2, 3, 4].map((item) => (
              <Skeleton key={item} className="h-10 w-full" />
            ))}
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon={<History className="h-5 w-5" aria-hidden="true" />}
            title="Chưa có lịch sử sử dụng"
            description="Chưa có lượt sử dụng AI nào trong khoảng thời gian đã chọn."
          />
        ) : (
          <>
            <div className="-mx-6 overflow-x-auto px-6">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <th className="pb-3 pr-4 font-semibold">Thời gian</th>
                    <th className="pb-3 pr-4 font-semibold">Tính năng</th>
                    <th className="pb-3 pr-4 text-right font-semibold">
                      Số lượt
                    </th>
                    <th className="pb-3 font-semibold">Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr
                      key={item.id}
                      className="border-b border-border/60 last:border-0"
                    >
                      <td className="whitespace-nowrap py-3 pr-4 text-muted-foreground">
                        {formatDateTime(item.created_at)}
                      </td>
                      <td className="py-3 pr-4 text-foreground">
                        {item.feature_label}
                      </td>
                      <td className="py-3 pr-4 text-right font-medium text-foreground">
                        {item.amount.toLocaleString('vi-VN')}
                      </td>
                      <td className="py-3">
                        <Badge
                          variant={STATUS_VARIANTS[item.status] ?? 'neutral'}
                        >
                          {item.status_label}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                Trang {data.page} / {Math.max(1, totalPages)} · {data.total} lượt
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={data.page <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  Trước
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={data.page >= totalPages}
                  onClick={() => setPage((current) => current + 1)}
                >
                  Sau
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
