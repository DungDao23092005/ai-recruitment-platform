import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart3,
  Briefcase,
  CalendarDays,
  CheckCircle2,
  Eye,
  EyeOff,
  Sparkles,
  TrendingUp,
  UserCheck,
  Users,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { getRecruiterAnalytics } from '@/api/analytics'
import type {
  AnalyticsFunnelStage,
  AnalyticsJobRow,
  AnalyticsQuotaLine,
  RecruiterAnalytics,
} from '@/types/analytics'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { isAxiosError } from 'axios'

const FUNNEL_LABELS: Record<AnalyticsFunnelStage['stage'], string> = {
  applied: 'Đã nộp',
  under_review: 'Đang xem xét',
  interviewing: 'Phỏng vấn',
  offered: 'Đề nghị nhận việc',
  accepted: 'Đã nhận việc',
}

const STAGE_COLORS: Record<AnalyticsFunnelStage['stage'], string> = {
  applied: 'bg-primary',
  under_review: 'bg-info',
  interviewing: 'bg-warning',
  offered: 'bg-accent',
  accepted: 'bg-success',
}

type AnalyticsState =
  | { kind: 'loading' }
  | { kind: 'no-company' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; data: RecruiterAnalytics }

function formatNumber(value: number): string {
  return value.toLocaleString('vi-VN')
}

function formatPercent(value: number): string {
  const normalized = value <= 1 ? value * 100 : value
  return `${normalized.toFixed(1)}%`
}

function formatDays(value: number | null): string {
  if (value === null) return '—'
  if (value < 1) return `${Math.round(value * 24)} giờ`
  return `${value.toFixed(1)} ngày`
}

interface KpiCardProps {
  icon: React.ReactNode
  title: string
  value: string
  description?: string
}

function KpiCard({ icon, title, value, description }: KpiCardProps) {
  return (
    <Card className="border-border/70">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="mt-1 font-display text-2xl font-bold tracking-tight">
              {value}
            </p>
            {description ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {description}
              </p>
            ) : null}
          </div>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function FunnelBars({ stages }: { stages: AnalyticsFunnelStage[] }) {
  const top = Math.max(1, ...stages.map((stage) => stage.count))
  return (
    <ol className="space-y-3" aria-label="Phễu tuyển dụng">
      {stages.map((stage) => {
        const width = Math.max(
          stage.count > 0 ? 4 : 0,
          Math.round((stage.count / top) * 100),
        )
        return (
          <li key={stage.stage}>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="font-medium">{FUNNEL_LABELS[stage.stage]}</span>
              <span className="tabular-nums text-muted-foreground">
                {formatNumber(stage.count)}
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${STAGE_COLORS[stage.stage]}`}
                style={{ width: `${width}%` }}
                role="img"
                aria-label={`${FUNNEL_LABELS[stage.stage]}: ${stage.count}`}
              />
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function DailyViewsChart({
  points,
}: {
  points: RecruiterAnalytics['daily_views']
}) {
  const max = Math.max(1, ...points.map((point) => point.total_views))
  if (points.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Chưa có dữ liệu lượt xem trong khoảng thời gian này.
      </p>
    )
  }
  return (
    <div>
      <div
        className="flex h-36 items-end gap-1"
        role="img"
        aria-label="Biểu đồ lượt xem theo ngày"
      >
        {points.map((point) => (
          <div
            key={point.date}
            className="group relative flex h-full flex-1 items-end"
            title={`${point.date}: ${point.total_views} lượt xem`}
          >
            <div
              className="w-full rounded-t bg-primary/70 transition-colors group-hover:bg-primary"
              style={{
                height: `${Math.max(
                  point.total_views > 0 ? 4 : 1,
                  (point.total_views / max) * 100,
                )}%`,
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted-foreground">
        <span>{points[0]?.date}</span>
        <span>{points[points.length - 1]?.date}</span>
      </div>
    </div>
  )
}

function QuotaRow({
  label,
  line,
  usedLabel,
}: {
  label: string
  line: AnalyticsQuotaLine
  usedLabel: string
}) {
  const unlimited = line.limit === null
  const percent =
    !unlimited && line.limit && line.limit > 0
      ? Math.min(100, Math.round((line.used / line.limit) * 100))
      : 0
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {unlimited
            ? `${formatNumber(line.used)} đã dùng · Không giới hạn`
            : `${formatNumber(line.used)} / ${formatNumber(line.limit ?? 0)}`}
        </span>
      </div>
      <Progress value={percent} aria-label={`${label} ${usedLabel}`} />
    </div>
  )
}

function JobsTable({ jobs }: { jobs: AnalyticsJobRow[] }) {
  if (jobs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Chưa có tin tuyển dụng nào trong khoảng thời gian này.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="py-2 pr-3 font-medium">Tin tuyển dụng</th>
            <th className="px-3 py-2 text-right font-medium">Lượt xem</th>
            <th className="px-3 py-2 text-right font-medium">Duy nhất</th>
            <th className="px-3 py-2 text-right font-medium">Ứng tuyển</th>
            <th className="py-2 pl-3 text-right font-medium">Nhận việc</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.job_id} className="border-b last:border-0">
              <td className="max-w-[18rem] py-2.5 pr-3">
                <p className="truncate font-medium">{job.job_title}</p>
                <p className="text-xs text-muted-foreground">{job.job_status}</p>
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums">
                {formatNumber(job.total_views)}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums">
                {formatNumber(job.unique_views)}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums">
                {formatNumber(job.applications)}
              </td>
              <td className="py-2.5 pl-3 text-right tabular-nums">
                {formatNumber(job.hires)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function RecruiterAnalyticsPage() {
  const [state, setState] = useState<AnalyticsState>({ kind: 'loading' })
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [appliedRange, setAppliedRange] = useState<{
    start_date?: string
    end_date?: string
  }>({})
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    setState({ kind: 'loading' })
    getRecruiterAnalytics(appliedRange)
      .then((data) => {
        if (active) setState({ kind: 'success', data })
      })
      .catch((err) => {
        if (!active) return
        if (isAxiosError(err) && err.response?.status === 404) {
          setState({ kind: 'no-company' })
          return
        }
        setState({ kind: 'error', message: getFriendlyErrorMessage(err) })
      })
    return () => {
      active = false
    }
  }, [appliedRange, reloadKey])

  const applyRange = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAppliedRange({
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    })
  }

  const resetRange = () => {
    setStartDate('')
    setEndDate('')
    setAppliedRange({})
  }

  const data = state.kind === 'success' ? state.data : null
  const isEmpty = useMemo(() => {
    if (!data) return false
    return (
      data.kpis.total_views === 0 &&
      data.kpis.total_applications === 0 &&
      data.jobs.length === 0
    )
  }, [data])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Phân tích tuyển dụng"
        description="Hiệu quả tin tuyển dụng theo lượt xem, phễu ứng tuyển và thời gian tuyển dụng."
        actions={
          <Link to="/recruiter/jobs">
            <Button variant="outline">
              <Briefcase className="h-4 w-4" aria-hidden="true" />
              Quản lý tin tuyển dụng
            </Button>
          </Link>
        }
      />

      <Card className="border-border/70">
        <CardContent className="p-4">
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={applyRange}
          >
            <div className="grid flex-1 gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="font-medium">Từ ngày</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                  className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium">Đến ngày</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                  className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                />
              </label>
            </div>
            <div className="flex gap-2">
              <Button type="submit">
                <CalendarDays className="h-4 w-4" aria-hidden="true" />
                Áp dụng
              </Button>
              <Button type="button" variant="ghost" onClick={resetRange}>
                Xoá lọc
              </Button>
            </div>
          </form>
          <p className="mt-3 text-xs text-muted-foreground">
            Mặc định 30 ngày gần nhất. Ngày được tính theo múi giờ Việt Nam
            (UTC+7). Bạn chỉ xem được dữ liệu của công ty mình.
          </p>
        </CardContent>
      </Card>

      {state.kind === 'loading' ? (
        <div className="space-y-4" aria-busy="true">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-28 w-full" />
            ))}
          </div>
          <Skeleton className="h-72 w-full" />
        </div>
      ) : null}

      {state.kind === 'no-company' ? (
        <EmptyState
          icon={<Briefcase className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có công ty"
          description="Hãy tạo công ty trước khi xem phân tích tuyển dụng."
        >
          <Link to="/recruiter/company">
            <Button>Tạo công ty</Button>
          </Link>
        </EmptyState>
      ) : null}

      {state.kind === 'error' ? (
        <ErrorBanner
          message={state.message}
          onRetry={() => setReloadKey((key) => key + 1)}
        />
      ) : null}

      {data && isEmpty ? (
        <EmptyState
          icon={<BarChart3 className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có dữ liệu phân tích"
          description="Dữ liệu sẽ xuất hiện khi ứng viên xem tin tuyển dụng hoặc nộp đơn. Hãy đăng tin để bắt đầu thu thập."
        >
          <Link to="/recruiter/jobs/new">
            <Button>Đăng tin tuyển dụng</Button>
          </Link>
        </EmptyState>
      ) : null}

      {data && !isEmpty ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              icon={<Eye className="h-5 w-5" aria-hidden="true" />}
              title="Lượt xem tin"
              value={formatNumber(data.kpis.total_views)}
              description={`${formatNumber(
                data.kpis.unique_views,
              )} lượt xem duy nhất`}
            />
            <KpiCard
              icon={<Users className="h-5 w-5" aria-hidden="true" />}
              title="Ứng tuyển"
              value={formatNumber(data.kpis.total_applications)}
              description={`Tỷ lệ chuyển đổi ${formatPercent(
                data.kpis.conversion_rate,
              )}`}
            />
            <KpiCard
              icon={<UserCheck className="h-5 w-5" aria-hidden="true" />}
              title="Nhận việc"
              value={formatNumber(data.kpis.hires)}
              description={`Thời gian tuyển dụng TB ${formatDays(
                data.kpis.avg_time_to_hire_days,
              )}`}
            />
            <KpiCard
              icon={<EyeOff className="h-5 w-5" aria-hidden="true" />}
              title="Lượt xem chưa xác minh"
              value={formatNumber(data.kpis.unverified_views)}
              description="Chưa đủ điều kiện tính là duy nhất"
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="border-border/70">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-primary" aria-hidden="true" />
                  Phễu tuyển dụng
                </CardTitle>
                <CardDescription>
                  Ứng viên đã nộp trong khoảng thời gian đã chọn, kèm trạng thái
                  hiện tại.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <FunnelBars stages={data.funnel} />
              </CardContent>
            </Card>

            <Card className="border-border/70">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3
                    className="h-5 w-5 text-primary"
                    aria-hidden="true"
                  />
                  Lượt xem theo ngày
                </CardTitle>
                <CardDescription>
                  Tổng lượt xem theo ngày (giờ Việt Nam).
                </CardDescription>
              </CardHeader>
              <CardContent>
                <DailyViewsChart points={data.daily_views} />
              </CardContent>
            </Card>
          </div>

          <Card className="border-border/70">
            <CardHeader>
              <CardTitle>Hiệu quả theo tin tuyển dụng</CardTitle>
              <CardDescription>
                Lượt xem, ứng tuyển và số người nhận việc của từng tin.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <JobsTable jobs={data.jobs} />
            </CardContent>
          </Card>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="border-border/70 lg:col-span-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles
                    className="h-5 w-5 text-primary"
                    aria-hidden="true"
                  />
                  Hạn mức gói dịch vụ
                </CardTitle>
                <CardDescription>
                  {data.quota.plan_name ?? 'Chưa có gói active'}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {data.quota.subscription_status === 'active' ? (
                  <>
                    <QuotaRow
                      label="Tin tuyển dụng"
                      line={data.quota.job_posts}
                      usedLabel="tin đã đăng"
                    />
                    <QuotaRow
                      label="Tìm ứng viên"
                      line={data.quota.candidate_searches}
                      usedLabel="lượt tìm"
                    />
                    <QuotaRow
                      label="Tính năng AI"
                      line={data.quota.ai_features}
                      usedLabel="lượt dùng"
                    />
                    {data.quota.expires_at ? (
                      <p className="text-xs text-muted-foreground">
                        Hết hạn:{' '}
                        {new Date(data.quota.expires_at).toLocaleDateString(
                          'vi-VN',
                        )}
                      </p>
                    ) : null}
                  </>
                ) : (
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm text-muted-foreground">
                      Bạn chưa có gói dịch vụ đang hoạt động.
                    </p>
                    <Link to="/plans">
                      <Button variant="outline">Xem các gói</Button>
                    </Link>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-border/70">
              <CardHeader>
                <CardTitle>Chất lượng dữ liệu</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-center gap-2">
                  {data.data_quality.unique_views_reliable ? (
                    <Badge variant="success">
                      <CheckCircle2
                        className="mr-1 h-3.5 w-3.5"
                        aria-hidden="true"
                      />
                      Lượt xem duy nhất đáng tin cậy
                    </Badge>
                  ) : (
                    <Badge variant="warning">Lượt xem duy nhất chưa đầy đủ</Badge>
                  )}
                </div>
                <p className="text-muted-foreground">
                  {data.data_quality.note}
                </p>
                {data.data_quality.raw_fallback_dates.length > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Ngày dùng dữ liệu tạm (chưa tổng hợp):{' '}
                    {data.data_quality.raw_fallback_dates.join(', ')}
                  </p>
                ) : null}
                <p className="text-xs text-muted-foreground">
                  Múi giờ: {data.timezone} · {data.start_date} →{' '}
                  {data.end_date}
                </p>
              </CardContent>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  )
}
