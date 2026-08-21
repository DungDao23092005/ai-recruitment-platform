import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Building,
  Briefcase,
  PlusCircle,
  Users,
  Sparkles,
  ArrowRight,
  FileText,
  Users as UsersIcon,
  TrendingUp,
  AlertCircle,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import { getRecruiterMetrics } from '@/api/metrics'
import type { RecruiterMetrics, ApplicationStatusCount } from '@/types/metrics'

const PORTAL_CARDS = [
  {
    to: '/recruiter/company',
    icon: Building,
    title: 'Quản lý công ty',
    description: 'Tạo và xem thông tin công ty của bạn trước khi đăng tin.',
    cta: 'Quản lý công ty',
    ai: false,
  },
  {
    to: '/recruiter/jobs',
    icon: Briefcase,
    title: 'Tin tuyển dụng',
    description: 'Xem và quản lý các tin tuyển dụng cùng ứng viên của bạn.',
    cta: 'Xem tin tuyển dụng',
    ai: false,
  },
  {
    to: '/recruiter/jobs/new',
    icon: PlusCircle,
    title: 'Đăng tin tuyển dụng',
    description:
      'Tạo tin tuyển dụng mới với sự hỗ trợ của AI bóc tách kỹ năng JD.',
    cta: 'Đăng tin',
    ai: true,
  },
  {
    to: '/recruiter/search/candidates',
    icon: Users,
    title: 'Tìm ứng viên AI',
    description:
      'Mô tả ứng viên bạn cần bằng ngôn ngữ tự nhiên — AI tìm hồ sơ theo ngữ nghĩa.',
    cta: 'Tìm kiếm ngữ nghĩa',
    ai: true,
  },
]

const FUNNEL_STAGES: Array<{
  key: ApplicationStatusCount['status']
  label: string
  icon: React.ReactNode
  variant: 'primary' | 'success' | 'warning' | 'danger'
}> = [
  { key: 'applied', label: 'Đã nộp', icon: <FileText className="h-4 w-4" />, variant: 'primary' },
  { key: 'under_review', label: 'Đang xem xét', icon: <UsersIcon className="h-4 w-4" />, variant: 'warning' },
  { key: 'shortlisted', label: 'Lọt vòng', icon: <TrendingUp className="h-4 w-4" />, variant: 'success' },
  { key: 'interviewing', label: 'Phỏng vấn', icon: <Briefcase className="h-4 w-4" />, variant: 'warning' },
  { key: 'accepted', label: 'Đã chấp nhận', icon: <Sparkles className="h-4 w-4" />, variant: 'success' },
  { key: 'rejected', label: 'Đã từ chối', icon: <AlertCircle className="h-4 w-4" />, variant: 'danger' },
  { key: 'withdrawn', label: 'Rút đơn', icon: <ArrowRight className="h-4 w-4" />, variant: 'primary' },
]

interface MetricCardProps {
  icon: React.ReactNode
  title: string
  value: number
  description?: string
  variant?: 'primary' | 'success' | 'warning' | 'danger'
}

function MetricCard({ icon, title, value, description, variant = 'primary' }: MetricCardProps) {
  const variantColors: Record<string, string> = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-success/10 text-success',
    warning: 'bg-warning/10 text-warning',
    danger: 'bg-destructive/10 text-destructive',
  }

  return (
    <Card className="border-border/70">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="font-display text-3xl font-bold mt-1">{value.toLocaleString()}</p>
            {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
          </div>
          <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${variantColors[variant]}`}>
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function FunnelStage({
  label,
  count,
  total,
  variant,
  icon,
}: {
  label: string
  count: number
  total: number
  variant: 'primary' | 'success' | 'warning' | 'danger'
  icon: React.ReactNode
}) {
  const percentage = total > 0 ? (count / total) * 100 : 0

  return (
    <div className="flex items-center gap-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted/50 text-muted-foreground">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium truncate">{label}</span>
          <span className="font-medium text-right whitespace-nowrap">
            {count.toLocaleString()} ({percentage.toFixed(0)}%)
          </span>
        </div>
        <Progress value={percentage} variant={variant} className="mt-1 h-1.5" />
      </div>
    </div>
  )
}

function MetricsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="border-border/70">
            <CardContent className="p-6">
              <Skeleton className="h-4 w-3/4 mb-2" />
              <Skeleton className="h-8 w-1/2" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="border-border/70">
        <CardHeader>
          <CardTitle className="font-display text-lg font-semibold">Quy trình ứng tuyển</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-8 w-8 rounded-lg" />
                <div className="flex-1">
                  <Skeleton className="h-4 w-1/4 mb-1" />
                  <Skeleton className="h-2 w-full" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card className="border-border/70">
        <CardHeader>
          <CardTitle className="font-display text-lg font-semibold">Thao tác nhanh</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2">
            {[1, 2, 3, 4].map((i) => (
              <Card key={i} className="border-border/70 p-4">
                <Skeleton className="h-5 w-1/2" />
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export function RecruiterPortalPage() {
  const [state, setState] = useState<{
    kind: 'loading' | 'error' | 'success' | 'empty'
    metrics?: RecruiterMetrics
    message?: string
  }>({ kind: 'loading' })

  const loadMetrics = async () => {
    setState({ kind: 'loading' })
    try {
      const metrics = await getRecruiterMetrics()
      if (
        metrics.total_jobs === 0 &&
        metrics.total_applications === 0 &&
        metrics.jobs_by_status.length === 0 &&
        metrics.applications_by_status.length === 0
      ) {
        setState({ kind: 'empty', metrics })
      } else {
        setState({ kind: 'success', metrics })
      }
    } catch (err) {
      setState({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Không thể tải dữ liệu',
      })
    }
  }

  useEffect(() => {
    loadMetrics()
  }, [])

  if (state.kind === 'loading') {
    return <MetricsSkeleton />
  }

  if (state.kind === 'error') {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Nhà tuyển dụng"
          title="Tổng quan tuyển dụng"
          description="Quản lý công ty, tin tuyển dụng và ứng viên với sự hỗ trợ của AI."
        />
        <ErrorBanner message={state.message || 'Đã xảy ra lỗi'} onRetry={loadMetrics} />
      </div>
    )
  }

  const metrics = state.metrics!
  const pendingCount = metrics.applications_by_status
    .filter((s) => ['applied', 'under_review'].includes(s.status))
    .reduce((sum, s) => sum + s.count, 0)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Tổng quan tuyển dụng"
        description="Quản lý công ty, tin tuyển dụng và ứng viên với sự hỗ trợ của AI."
        actions={
          <Link to="/recruiter/jobs/new">
            <Button>
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              Đăng tin tuyển dụng
            </Button>
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          icon={<Briefcase className="h-5 w-5" />}
          title="Tổng tin tuyển dụng"
          value={metrics.total_jobs}
          variant="primary"
        />
        <MetricCard
          icon={<Briefcase className="h-5 w-5" />}
          title="Đang tuyển"
          value={
            metrics.jobs_by_status
              .filter((s) => s.status === 'published')
              .reduce((sum, s) => sum + s.count, 0)
          }
          variant="success"
        />
        <MetricCard
          icon={<FileText className="h-5 w-5" />}
          title="Tổng ứng tuyển"
          value={metrics.total_applications}
          variant="warning"
        />
        <MetricCard
          icon={<UsersIcon className="h-5 w-5" />}
          title="Cần xử lý"
          value={pendingCount}
          description="Applied + Under Review"
          variant="danger"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-border/70">
          <CardHeader>
            <CardTitle className="font-display text-lg font-semibold">Tin tuyển dụng theo trạng thái</CardTitle>
          </CardHeader>
          <CardContent>
            {metrics.jobs_by_status.length > 0 ? (
              <div className="space-y-3">
                {metrics.jobs_by_status.map((item) => (
                  <div key={item.status} className="flex items-center justify-between text-sm">
                    <Badge variant="outline-ai" className="w-32 shrink-0">
                      {item.status}
                    </Badge>
                    <span className="font-medium text-right">{item.count.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                Chưa có tin tuyển dụng nào.
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="border-border/70">
          <CardHeader>
            <CardTitle className="font-display text-lg font-semibold">Ứng tuyển theo trạng thái</CardTitle>
          </CardHeader>
          <CardContent>
            {metrics.applications_by_status.length > 0 ? (
              <div className="space-y-3">
                {metrics.applications_by_status.map((item) => (
                  <div key={item.status} className="flex items-center justify-between text-sm">
                    <Badge variant="outline-ai" className="w-32 shrink-0">
                      {item.status}
                    </Badge>
                    <span className="font-medium text-right">{item.count.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                Chưa có ứng tuyển nào.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/70">
        <CardHeader>
          <CardTitle className="font-display text-lg font-semibold">Quy trình ứng tuyển</CardTitle>
        </CardHeader>
        <CardContent>
          {metrics.total_applications > 0 ? (
            <div className="space-y-3">
              {FUNNEL_STAGES.map((stage) => {
                const stageData = metrics.applications_by_status.find(
                  (s) => s.status === stage.key
                )
                const count = stageData?.count ?? 0
                return (
                  <FunnelStage
                    key={stage.key}
                    label={stage.label}
                    count={count}
                    total={metrics.total_applications}
                    variant={stage.variant}
                    icon={stage.icon}
                  />
                )
              })}
            </div>
          ) : (
            <EmptyState
              icon={<FileText className="h-8 w-8" />}
              title="Chưa có ứng tuyển nào"
              description="Ứng tuyển sẽ hiển thị ở đây khi ứng viên nộp đơn cho các tin tuyển dụng của bạn."
            />
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70">
        <CardHeader>
          <CardTitle className="font-display text-lg font-semibold">Thao tác nhanh</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2">
            {PORTAL_CARDS.map((card) => (
              <Card
                key={card.to}
                className="group border-border/70 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft"
              >
                <CardHeader className="gap-3">
                  <div className="flex items-center justify-between">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <card.icon className="h-5 w-5" aria-hidden="true" />
                    </div>
                    {card.ai ? <Badge variant="ai-gradient">AI</Badge> : null}
                  </div>
                  <CardTitle className="font-display text-lg font-semibold">
                    {card.title}
                  </CardTitle>
                  <CardDescription>{card.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Link to={card.to}>
                    <Button
                      variant={card.ai ? 'default' : 'outline'}
                      className="w-full"
                    >
                      {card.cta}
                      <ArrowRight className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}