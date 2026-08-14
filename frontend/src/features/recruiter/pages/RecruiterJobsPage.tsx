import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getJobs } from '@/api/jobs'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { RecruiterJobCard } from '@/features/recruiter/components/RecruiterJobCard'
import type { Job } from '@/types/job'

type JobsState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; jobs: Job[] }

export function RecruiterJobsPage() {
  const [state, setState] = useState<JobsState>({ kind: 'loading' })

  useEffect(() => {
    let active = true
    setState({ kind: 'loading' })

    getJobs({ skip: 0, limit: 50 })
      .then((jobs) => {
        if (active) setState({ kind: 'success', jobs })
      })
      .catch((err) => {
        if (!active) return
        const message =
          err instanceof Error ? err.message : 'Unable to load jobs'
        setState({ kind: 'error', message })
      })

    return () => {
      active = false
    }
  }, [])

  return (
    <div className="container py-10">
      <PageHeader
        title="Job Postings"
        description="Manage your job postings and their applicants."
        actions={
          <Link to="/recruiter/jobs/new">
            <Button>Post a job</Button>
          </Link>
        }
      />

      {state.kind === 'loading' ? (
        <div className="flex min-h-[40vh] items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : null}

      {state.kind === 'error' ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
          <p className="text-sm font-medium text-destructive">
            {state.message}
          </p>
          <p className="text-sm text-muted-foreground">
            Unable to load jobs right now.
          </p>
        </div>
      ) : null}

      {state.kind === 'success' ? (
        state.jobs.length === 0 ? (
          <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
            <p className="text-sm text-muted-foreground">
              No jobs yet. Create your first job posting.
            </p>
            <Link to="/recruiter/jobs/new">
              <Button variant="outline">Post a job</Button>
            </Link>
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {state.jobs.map((job) => (
              <RecruiterJobCard key={job.id} job={job} />
            ))}
          </div>
        )
      ) : null}
    </div>
  )
}
