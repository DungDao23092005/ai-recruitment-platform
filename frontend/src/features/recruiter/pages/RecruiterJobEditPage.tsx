import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, FileText } from 'lucide-react'
import { getMyJobById } from '@/api/jobs'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import {
  Card,
  CardContent,
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
        description="Cập nhật thông tin tin tuyển dụng của bạn."
        actions={
          <Link to={backPath}>
            <Button variant="ghost">
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              Quay lại danh sách
            </Button>
          </Link>
        }
      />

      {state.kind === 'loading' ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
              Thông tin tin tuyển dụng
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
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
            <Link to="/recruiter/jobs">
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
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
              Thông tin tin tuyển dụng
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>Trạng thái hiện tại:</span>
              <Badge variant={JOB_STATUS_VARIANT[state.job.status]}>
                {JOB_STATUS_LABELS[state.job.status]}
              </Badge>
              <span>·</span>
              <span>{JOB_TYPE_LABELS[state.job.job_type]}</span>
            </div>
          </CardHeader>
          <CardContent>
            <JobForm
              companyId={state.job.company_id}
              job={state.job}
              onSaved={() => navigate(backPath)}
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}