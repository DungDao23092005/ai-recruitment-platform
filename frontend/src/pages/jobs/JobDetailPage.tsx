import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Briefcase,
  Building2,
  CalendarDays,
  MapPin,
} from 'lucide-react'
import { getJobById } from '@/api/jobs'
import { useAuth } from '@/contexts/AuthContext'
import { ApplyModal } from '@/features/jobs/components/ApplyModal'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Card,
  CardContent,
  CardHeader,
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

function companyMonogram(companyName: string): string {
  const trimmed = companyName.trim()
  if (!trimmed) {
    return 'C'
  }
  const words = trimmed.split(/\s+/)
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase()
  }
  return (
    words
      .slice(0, 2)
      .map((word) => word[0])
      .join('')
      .toUpperCase()
  )
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
      <div className="container mx-auto max-w-5xl py-10">
        <Skeleton className="h-4 w-32" />
        <div className="mt-6 grid gap-8 lg:grid-cols-[1fr_300px]">
          <div className="space-y-3">
            <Skeleton className="h-9 w-3/4" />
            <Skeleton className="h-5 w-1/3" />
            <Skeleton className="mt-6 h-64 w-full" />
          </div>
          <div className="space-y-3">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
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
  const postedDate = formatPostedDate(job.created_at)
  const rawCompanyName = job.company_name ?? `Công ty ${job.company_id.slice(0, 8)}`
  const companyLabel = job.company_name
    ? `Công ty ${job.company_name}`
    : rawCompanyName
  const isBlockedRole = Boolean(
    currentUser && currentUser.role !== 'candidate',
  )
  const isLoggedOut = !currentUser

  return (
    <div className="container mx-auto max-w-5xl py-10">
      <div className="mb-6">
        <Link to="/jobs">
          <Button variant="ghost" size="sm" className="text-muted-foreground">
            <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
            Quay lại danh sách
          </Button>
        </Link>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        <div className="space-y-6">
          <Card className="border-border/70 shadow-soft">
            <CardHeader className="gap-4">
              <div className="flex items-start gap-4">
                <div
                  className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-primary/10 font-display text-lg font-bold text-primary ring-1 ring-primary/15"
                  aria-hidden="true"
                >
                  {companyMonogram(rawCompanyName)}
                </div>
                <div className="min-w-0">
                  <h1 className="font-display text-2xl font-bold leading-tight tracking-tight sm:text-3xl">
                    {job.title}
                  </h1>
                  <p className="mt-1.5 flex items-center gap-1.5 text-sm text-muted-foreground">
                    <Building2
                      className="h-4 w-4 text-primary/70"
                      aria-hidden="true"
                    />
                    {companyLabel}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="neutral">{JOB_TYPE_LABELS[job.job_type]}</Badge>
                <Badge variant="neutral">
                  {WORKPLACE_TYPE_LABELS[job.workplace_type]}
                </Badge>
                <Badge variant="outline-ai">{JOB_STATUS_LABELS[job.status]}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div>
                <h2 className="mb-2 font-display text-lg font-semibold">
                  Mô tả công việc
                </h2>
                <p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
                  {job.description}
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <Card className="border-border/70 shadow-soft">
            <CardContent className="space-y-4 pt-6">
              <div className="flex items-center gap-3">
                <MapPin className="h-4 w-4 text-primary" aria-hidden="true" />
                <div>
                  <p className="text-xs text-muted-foreground">Địa điểm</p>
                  <p className="text-sm font-medium">{job.location}</p>
                </div>
              </div>
              {postedDate ? (
                <div className="flex items-center gap-3">
                  <CalendarDays
                    className="h-4 w-4 text-primary"
                    aria-hidden="true"
                  />
                  <div>
                    <p className="text-xs text-muted-foreground">Ngày đăng</p>
                    <p className="text-sm font-medium">{postedDate}</p>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="border-primary/20 bg-primary/5 shadow-soft">
            <CardContent className="space-y-3 pt-6">
              <Button
                onClick={handleApply}
                disabled={isBlockedRole}
                size="lg"
                className="w-full"
              >
                <Briefcase className="h-4 w-4" aria-hidden="true" />
                Ứng tuyển ngay
              </Button>
              {isBlockedRole ? (
                <p className="text-center text-xs text-muted-foreground">
                  Chỉ ứng viên mới có thể ứng tuyển.
                </p>
              ) : null}
              {isLoggedOut ? (
                <p className="text-center text-xs text-muted-foreground">
                  Đăng nhập với tài khoản ứng viên để ứng tuyển.
                </p>
              ) : null}
            </CardContent>
          </Card>
        </aside>
      </div>

      {showApply ? (
        <ApplyModal job={job} onClose={() => setShowApply(false)} />
      ) : null}
    </div>
  )
}