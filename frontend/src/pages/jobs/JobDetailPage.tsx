import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { MapPin, Briefcase, Building, ArrowLeft } from 'lucide-react'
import { getJobById } from '@/api/jobs'
import { useAuth } from '@/contexts/AuthContext'
import { ApplyModal } from '@/features/jobs/components/ApplyModal'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  WORKPLACE_TYPE_LABELS,
} from '@/types/job'
import type { Job } from '@/types/job'

type JobState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; notFound: boolean }
  | { kind: 'success'; job: Job }

function formatPostedDate(dateString: string): string {
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleDateString('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { currentUser } = useAuth()
  const [state, setState] = useState<JobState>({ kind: 'loading' })
  const [showApply, setShowApply] = useState(false)

  useEffect(() => {
    if (!id) {
      setState({ kind: 'error', message: 'Không tìm thấy công việc', notFound: true })
      return
    }

    let active = true
    setState({ kind: 'loading' })

    getJobById(id)
      .then((job) => {
        if (active) setState({ kind: 'success', job })
      })
      .catch((err) => {
        if (!active) return
        const status = (err as Error & { response?: { status?: number } })
          .response?.status
        const notFound = status === 404
        setState({
          kind: 'error',
          message: notFound
            ? 'Không tìm thấy công việc'
            : 'Không thể tải công việc này.',
          notFound,
        })
      })

    return () => {
      active = false
    }
  }, [id])

  const handleApply = () => {
    if (!currentUser) {
      navigate('/login', { state: { from: `/jobs/${id}` } })
      return
    }
    if (currentUser.role !== 'candidate') {
      return
    }
    setShowApply(true)
  }

  if (state.kind === 'loading') {
    return (
      <div className="container mx-auto max-w-3xl py-10">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="mt-4 h-8 w-3/4" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="mt-6 h-40 w-full" />
        </div>
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <div className="container flex min-h-[50vh] flex-col items-center justify-center py-10 text-center">
        <p className="font-display text-6xl font-bold ai-text">
          {state.notFound ? '404' : 'Lỗi'}
        </p>
        <h1 className="mt-4 font-display text-2xl font-bold tracking-tight">
          {state.message}
        </h1>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          {state.notFound
            ? 'Công việc bạn đang tìm không tồn tại hoặc đã bị gỡ.'
            : 'Đã xảy ra lỗi khi tải công việc này.'}
        </p>
        <Link to="/jobs" className="mt-6">
          <Button variant="outline">Quay lại danh sách việc làm</Button>
        </Link>
      </div>
    )
  }

  const { job } = state

  return (
    <div className="container mx-auto max-w-3xl py-10">
      <div className="mb-6">
        <Link to="/jobs">
          <Button variant="ghost" size="sm" className="text-muted-foreground">
            <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
            Quay lại danh sách
          </Button>
        </Link>
      </div>

      <Card className="border-border/70 shadow-soft">
        <CardHeader className="gap-3">
          <CardTitle className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
            {job.title}
          </CardTitle>
          <CardDescription className="flex items-center gap-1.5 text-sm">
            <Building className="h-4 w-4 text-primary/70" aria-hidden="true" />
            Công ty {job.company_name ?? job.company_id.slice(0, 8)}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="neutral">{JOB_TYPE_LABELS[job.job_type]}</Badge>
            <Badge variant="neutral">
              {WORKPLACE_TYPE_LABELS[job.workplace_type]}
            </Badge>
            <Badge variant="ai-gradient">{JOB_STATUS_LABELS[job.status]}</Badge>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <MapPin className="h-4 w-4" aria-hidden="true" />
              {job.location}
            </span>
            {formatPostedDate(job.created_at) ? (
              <span className="text-xs">Đăng {formatPostedDate(job.created_at)}</span>
            ) : null}
          </div>

          <div>
            <h2 className="mb-2 font-display text-lg font-semibold">
              Mô tả công việc
            </h2>
            <p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
              {job.description}
            </p>
          </div>

          <div className="flex items-center gap-3 border-t pt-6">
            <Button
              onClick={handleApply}
              disabled={
                currentUser?.role === 'recruiter' ||
                currentUser?.role === 'admin'
              }
            >
              <Briefcase className="h-4 w-4" aria-hidden="true" />
              Ứng tuyển ngay
            </Button>
            {currentUser?.role === 'recruiter' ||
            currentUser?.role === 'admin' ? (
              <span className="text-sm text-muted-foreground">
                Chỉ ứng viên mới có thể ứng tuyển.
              </span>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {showApply ? (
        <ApplyModal job={job} onClose={() => setShowApply(false)} />
      ) : null}
    </div>
  )
}