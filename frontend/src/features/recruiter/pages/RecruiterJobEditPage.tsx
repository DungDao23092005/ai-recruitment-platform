import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Briefcase, ChevronLeft, FileText } from 'lucide-react'
import { getMyJobById } from '@/api/jobs'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { JobForm } from '@/features/recruiter/components/JobForm'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { JOB_STATUS_LABELS, JOB_TYPE_LABELS } from '@/types/job'
import type { Job, JobStatus } from '@/types/job'

const JOB_STATUS_VARIANT: Record<
  JobStatus,
  'neutral' | 'success' | 'warning' | 'destructive'
> = {
  draft: 'neutral',
  published: 'success',
  closed: 'warning',
  expired: 'destructive',
}

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; notFound: boolean }
  | { kind: 'success'; job: Job }

interface RecruiterJobEditPageProps {
  backPath?: string
}

export function RecruiterJobEditPage({ backPath = '/recruiter/jobs' }: RecruiterJobEditPageProps) {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [state, setState] = useState<PageState>({ kind: 'loading' })

  const load = useCallback(() => {
    if (!id) {
      setState({
        kind: 'error',
        message: 'Không tìm thấy tin tuyển dụng',
        notFound: true,
      })
      return
    }

    setState({ kind: 'loading' })

    getMyJobById(id)
      .then((job) => {
        setState({ kind: 'success', job })
      })
      .catch((err) => {
        const status = (err as Error & { response?: { status?: number } })
          .response?.status
        const notFound = status === 404
        setState({
          kind: 'error',
          message: notFound
            ? 'Không tìm thấy tin tuyển dụng'
            : getFriendlyErrorMessage(err),
          notFound,
        })
      })
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Sửa tin tuyển dụng"
        description="Cập nhật thông tin chi tiết và thời hạn tin tuyển dụng của bạn."
        actions={
          <Link to={backPath}>
            <Button variant="outline" size="sm" className="gap-1.5">
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              Quay lại danh sách
            </Button>
          </Link>
        }
      />

      {state.kind === 'loading' ? (
        <Card className="border-border/80 shadow-sm">
          <CardHeader className="p-6">
            <CardTitle className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
              <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
              Thông tin tin tuyển dụng
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 p-6 pt-0">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      ) : null}

      {state.kind === 'error' ? (
        state.notFound ? (
          <EmptyState
            icon={<FileText className="h-6 w-6" aria-hidden="true" />}
            title="Không tìm thấy tin tuyển dụng"
            description="Tin tuyển dụng có thể đã bị xóa hoặc bạn không có quyền truy cập."
          >
            <Link to={backPath}>
              <Button>
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Quay lại danh sách
              </Button>
            </Link>
          </EmptyState>
        ) : (
          <ErrorBanner message={state.message} onRetry={load} />
        )
      ) : null}

      {state.kind === 'success' ? (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/80 bg-card px-5 py-3.5 shadow-xs">
            <div className="flex items-center gap-3.5 min-w-0">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 font-display text-base font-bold text-primary select-none"
                aria-hidden="true"
              >
                <Briefcase className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="min-w-0 space-y-0.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-base font-bold text-foreground truncate">
                    {state.job.title}
                  </span>
                  <Badge variant={JOB_STATUS_VARIANT[state.job.status]}>
                    {JOB_STATUS_LABELS[state.job.status]}
                  </Badge>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {state.job.company_name ? (
                    <>
                      <span className="font-medium text-foreground">{state.job.company_name}</span>
                      <span>•</span>
                    </>
                  ) : null}
                  <span>{JOB_TYPE_LABELS[state.job.job_type]}</span>
                  {state.job.expires_at ? (
                    <>
                      <span>•</span>
                      <span>
                        Hạn: {new Date(state.job.expires_at).toLocaleDateString('vi-VN')}
                      </span>
                    </>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          <Card className="border-border/80 shadow-sm">
            <CardHeader className="p-6">
              <CardTitle className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
                <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
                Thông tin tin tuyển dụng
              </CardTitle>
              <CardDescription>
                Chỉnh sửa các tiêu chí, yêu cầu kỹ năng và thời gian tuyển dụng cho vị trí này.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-6 pt-0">
              <JobForm
                companyId={state.job.company_id}
                job={state.job}
                onSaved={() => navigate(backPath)}
              />
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  )
}
