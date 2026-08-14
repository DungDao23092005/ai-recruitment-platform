import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { MapPin, Briefcase, Building } from 'lucide-react'
import { getJobById } from '@/api/jobs'
import { useAuth } from '@/contexts/AuthContext'
import { ApplyModal } from '@/features/jobs/components/ApplyModal'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { JOB_TYPE_LABELS, WORKPLACE_TYPE_LABELS } from '@/types/job'
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
  return date.toLocaleDateString(undefined, {
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
      setState({ kind: 'error', message: 'Job not found', notFound: true })
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
          message: notFound ? 'Job not found' : 'Unable to load this job.',
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
      <div className="flex min-h-[50vh] items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <div className="container flex min-h-[50vh] flex-col items-center justify-center py-10 text-center">
        <p className="text-5xl font-bold text-primary">
          {state.notFound ? '404' : 'Error'}
        </p>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight">
          {state.message}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {state.notFound
            ? 'The job you are looking for does not exist.'
            : 'Something went wrong while loading this job.'}
        </p>
        <Link to="/jobs" className="mt-6">
          <Button variant="outline">Back to jobs</Button>
        </Link>
      </div>
    )
  }

  const { job } = state

  return (
    <div className="container py-10">
      <div className="mb-6 flex items-center gap-2">
        <Link to="/jobs">
          <Button variant="ghost" size="sm">
            &larr; Back to jobs
          </Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">{job.title}</CardTitle>
          <CardDescription className="flex items-center gap-1">
            <Building className="h-4 w-4" aria-hidden="true" />
            <span className="text-xs uppercase">
              Company ID: {job.company_id.slice(0, 8)}
            </span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="neutral">{JOB_TYPE_LABELS[job.job_type]}</Badge>
            <Badge variant="neutral">
              {WORKPLACE_TYPE_LABELS[job.workplace_type]}
            </Badge>
            <Badge variant="ai-gradient">{job.status}</Badge>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <MapPin className="h-4 w-4" aria-hidden="true" />
              {job.location}
            </span>
            {formatPostedDate(job.created_at) ? (
              <span className="text-xs">
                Posted {formatPostedDate(job.created_at)}
              </span>
            ) : null}
          </div>

          <div>
            <h2 className="mb-2 text-lg font-semibold">Description</h2>
            <p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
              {job.description}
            </p>
          </div>

          <div className="flex items-center gap-3 border-t pt-6">
            <Button
              onClick={handleApply}
              disabled={currentUser?.role === 'recruiter' || currentUser?.role === 'admin'}
            >
              <Briefcase className="h-4 w-4" aria-hidden="true" />
              Apply now
            </Button>
            {currentUser?.role === 'recruiter' ||
            currentUser?.role === 'admin' ? (
              <span className="text-sm text-muted-foreground">
                Only candidates can apply for jobs.
              </span>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {showApply ? (
        <ApplyModal
          job={job}
          onClose={() => setShowApply(false)}
        />
      ) : null}
    </div>
  )
}