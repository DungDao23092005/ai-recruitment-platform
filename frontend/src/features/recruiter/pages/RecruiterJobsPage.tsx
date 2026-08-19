import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Briefcase, PlusCircle } from 'lucide-react'
import { getMyJobs } from '@/api/jobs'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import { RecruiterJobCard } from '@/features/recruiter/components/RecruiterJobCard'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { Job } from '@/types/job'

type JobsState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; jobs: Job[] }

export function RecruiterJobsPage() {
  const [state, setState] = useState<JobsState>({ kind: 'loading' })

  const load = () => {
    setState({ kind: 'loading' })

    getMyJobs({ skip: 0, limit: 50 })
      .then((jobs) => {
        setState({ kind: 'success', jobs })
      })
      .catch((err) => {
        setState({
          kind: 'error',
          message: getFriendlyErrorMessage(err),
        })
      })
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Tin tuyển dụng"
        description="Quản lý các tin tuyển dụng và ứng viên của bạn."
        actions={
          <Link to="/recruiter/jobs/new">
            <Button>
              <PlusCircle className="h-4 w-4" aria-hidden="true" />
              Đăng tin tuyển dụng
            </Button>
          </Link>
        }
      />

      {state.kind === 'loading' ? (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={index}
              className="space-y-3 rounded-xl border bg-card p-5"
            >
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-16 w-full" />
              <div className="flex gap-2 pt-2">
                <Skeleton className="h-9 w-full" />
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {state.kind === 'error' ? (
        <ErrorBanner message={state.message} onRetry={load} />
      ) : null}

      {state.kind === 'success' ? (
        state.jobs.length === 0 ? (
          <EmptyState
            icon={<Briefcase className="h-6 w-6" aria-hidden="true" />}
            title="Chưa có tin tuyển dụng"
            description="Tạo tin tuyển dụng đầu tiên của bạn để bắt đầu nhận hồ sơ ứng viên."
          >
            <Link to="/recruiter/jobs/new">
              <Button>
                <PlusCircle className="h-4 w-4" aria-hidden="true" />
                Đăng tin tuyển dụng
              </Button>
            </Link>
          </EmptyState>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {state.jobs.map((job) => (
              <RecruiterJobCard key={job.id} job={job} onMutated={load} />
            ))}
          </div>
        )
      ) : null}
    </div>
  )
}