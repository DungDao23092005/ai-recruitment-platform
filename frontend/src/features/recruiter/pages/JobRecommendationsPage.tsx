import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { getJobById } from '@/api/jobs'
import { getCandidateRecommendations } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { CandidateRecommendationCard } from '@/features/ai/components/CandidateRecommendationCard'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { CandidateMatchRecommendation } from '@/types/ai'
import type { Job } from '@/types/job'

const DEFAULT_LIMIT = 10

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; notFound: boolean }
  | {
      kind: 'success'
      job: Job
      recommendations: CandidateMatchRecommendation[]
    }

export function JobRecommendationsPage() {
  const { id } = useParams<{ id: string }>()
  const [state, setState] = useState<PageState>({ kind: 'loading' })

  const load = useCallback(() => {
    if (!id) {
      setState({ kind: 'error', message: 'Job not found', notFound: true })
      return
    }

    setState({ kind: 'loading' })

    Promise.all([getJobById(id), getCandidateRecommendations(id, DEFAULT_LIMIT)])
      .then(([job, recommendations]) => {
        const sorted = [...recommendations].sort(
          (a, b) => b.match_result.overall_score - a.match_result.overall_score,
        )
        setState({ kind: 'success', job, recommendations: sorted })
      })
      .catch((err) => {
        const status = (err as Error & { response?: { status?: number } })
          .response?.status
        const notFound = status === 404
        setState({
          kind: 'error',
          message: notFound ? 'Job not found' : getFriendlyErrorMessage(err),
          notFound,
        })
      })
  }, [id])

  useEffect(() => {
    load()
  }, [load])

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
            : 'Something went wrong while loading recommendations.'}
        </p>
        <div className="mt-6 flex items-center gap-3">
          {state.notFound ? (
            <Link to="/recruiter/jobs">
              <Button variant="outline">Back to jobs</Button>
            </Link>
          ) : (
            <Button variant="outline" onClick={load}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Thử lại
            </Button>
          )}
        </div>
      </div>
    )
  }

  const { job, recommendations } = state

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
        title="Gợi ý Ứng viên AI"
        description={`Top candidates được AI gợi ý cho tin tuyển dụng "${job.title}".`}
      />

      {recommendations.length === 0 ? (
        <div className="flex min-h-[30vh] items-center justify-center text-center">
          <p className="max-w-md text-sm text-muted-foreground">
            Chưa tìm thấy ứng viên phù hợp với yêu cầu của tin tuyển dụng
            này.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {recommendations.map((recommendation) => (
            <CandidateRecommendationCard
              key={recommendation.candidate_id}
              recommendation={recommendation}
            />
          ))}
        </div>
      )}
    </div>
  )
}