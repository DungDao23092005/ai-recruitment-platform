import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, RefreshCw, Users } from 'lucide-react'
import { getMyJobById } from '@/api/jobs'
import { getApplicationsByJob } from '@/api/applications'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ApplicantList } from '@/features/recruiter/components/ApplicantList'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { JOB_STATUS_LABELS, JOB_TYPE_LABELS } from '@/types/job'
import type { Job, JobStatus } from '@/types/job'
import type { Application } from '@/types/application'

const JOB_STATUS_VARIANT: Record<JobStatus, 'neutral' | 'success' | 'warning' | 'destructive'> = {
  draft: 'neutral',
  published: 'success',
  closed: 'warning',
  expired: 'destructive',
}

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; notFound: boolean }
  | { kind: 'success'; job: Job; applications: Application[] }

interface JobApplicantsPageProps {
  backPath?: string
}

export function JobApplicantsPage({ backPath = '/recruiter/jobs' }: JobApplicantsPageProps) {
  const { id } = useParams<{ id: string }>()
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

    let active = true
    setState({ kind: 'loading' })

    Promise.all([getMyJobById(id), getApplicationsByJob(id)])
      .then(([job, applications]) => {
        if (active) setState({ kind: 'success', job, applications })
      })
      .catch((err) => {
        if (!active) return
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

    return () => {
      active = false
    }
  }, [id])

  useEffect(() => {
    return load()
  }, [load])

  if (state.kind === 'loading') {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-1/2" />
        <Skeleton className="h-20 w-full" />
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 text-center">
        <div>
          <p className="text-5xl font-bold text-primary">
            {state.notFound ? '404' : 'Lỗi'}
          </p>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">
            {state.message}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {state.notFound
              ? 'Tin tuyển dụng bạn tìm kiếm không tồn tại.'
              : 'Đã xảy ra lỗi khi tải danh sách ứng viên.'}
          </p>
        </div>
        {state.notFound ? (
          <Link to={backPath}>
            <Button variant="outline">Quay lại tin tuyển dụng</Button>
          </Link>
        ) : (
          <Button variant="outline" onClick={load}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Thử lại
          </Button>
        )}
      </div>
    )
  }

  const { job, applications } = state

  return (
    <div className="space-y-6">
      <Link to={backPath}>
        <Button variant="ghost" size="sm">
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Quay lại tin tuyển dụng
        </Button>
      </Link>

      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Ứng viên"
        description={`Quản lý đơn ứng tuyển cho tin tuyển dụng "${job.title}".`}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{job.title}</CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-2">
            <Badge variant={JOB_STATUS_VARIANT[job.status]}>
              {JOB_STATUS_LABELS[job.status]}
            </Badge>
            <span className="text-xs uppercase text-muted-foreground">
              {JOB_TYPE_LABELS[job.job_type]}
            </span>
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {job.location}
        </CardContent>
      </Card>

      {applications.length === 0 ? (
        <EmptyState
          icon={<Users className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có ứng viên"
          description="Tin tuyển dụng này chưa nhận được đơn ứng tuyển nào."
        />
      ) : (
        <ApplicantList applications={applications} />
      )}
    </div>
  )
}