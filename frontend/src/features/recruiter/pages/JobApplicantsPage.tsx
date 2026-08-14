import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getJobById } from '@/api/jobs'
import { getApplicationsByJob } from '@/api/applications'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
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
import type { Application } from '@/types/application'
import type { Job } from '@/types/job'

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; notFound: boolean }
  | { kind: 'success'; job: Job; applications: Application[] }

export function JobApplicantsPage() {
  const { id } = useParams<{ id: string }>()
  const [state, setState] = useState<PageState>({ kind: 'loading' })

  useEffect(() => {
    if (!id) {
      setState({ kind: 'error', message: 'Job not found', notFound: true })
      return
    }

    let active = true
    setState({ kind: 'loading' })

    Promise.all([getJobById(id), getApplicationsByJob(id)])
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
            ? 'Job not found'
            : getFriendlyErrorMessage(err),
          notFound,
        })
      })

    return () => {
      active = false
    }
  }, [id])

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
            : 'Something went wrong while loading applicants.'}
        </p>
        <Link to="/recruiter/jobs" className="mt-6">
          <Button variant="outline">Back to jobs</Button>
        </Link>
      </div>
    )
  }

  const { job, applications } = state

  return (
    <div className="container py-10">
      <div className="mb-6 flex items-center gap-2">
        <Link to="/recruiter/jobs">
          <Button variant="ghost" size="sm">
            &larr; Back to jobs
          </Button>
        </Link>
      </div>

      <PageHeader
        title="Applicants"
        description={`Manage applications for "${job.title}".`}
      />

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-xl">{job.title}</CardTitle>
          <CardDescription className="flex items-center gap-2">
            <Badge variant="ai-gradient">
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

      <ApplicantList applications={applications} />
    </div>
  )
}