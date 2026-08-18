import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileUp, Sparkles } from 'lucide-react'
import { getJobRecommendations } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import { JobRecommendationCard } from '@/features/ai/components/JobRecommendationCard'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { JobMatchRecommendation } from '@/types/ai'

const DEFAULT_LIMIT = 10

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; recommendations: JobMatchRecommendation[] }

export function CandidateRecommendationsPage() {
  const [state, setState] = useState<PageState>({ kind: 'loading' })

  const load = useCallback(() => {
    setState({ kind: 'loading' })

    getJobRecommendations(DEFAULT_LIMIT)
      .then((recommendations) => {
        const sorted = [...recommendations].sort(
          (a, b) => b.match_result.overall_score - a.match_result.overall_score,
        )
        setState({ kind: 'success', recommendations: sorted })
      })
      .catch((err) => {
        setState({
          kind: 'error',
          message: getFriendlyErrorMessage(err),
        })
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Ứng viên"
        title="Việc làm phù hợp với bạn"
        description="Top công việc được AI gợi ý dựa trên kỹ năng và kinh nghiệm của bạn."
      />

      {state.kind === 'loading' ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-64 w-full" />
          ))}
        </div>
      ) : null}

      {state.kind === 'error' ? (
        <ErrorBanner message={state.message} onRetry={load} />
      ) : null}

      {state.kind === 'success' ? (
        state.recommendations.length === 0 ? (
          <EmptyState
            icon={<Sparkles className="h-6 w-6" aria-hidden="true" />}
            title="Chưa có gợi ý việc làm"
            description="Chưa có gợi ý việc làm phù hợp. Hãy tải lên CV PDF để AI phân tích kỹ năng của bạn!"
          >
            <Link to="/candidate/cv-upload">
              <Button>
                <FileUp className="h-4 w-4" aria-hidden="true" />
                Tải lên CV
              </Button>
            </Link>
          </EmptyState>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {state.recommendations.map((recommendation) => (
              <JobRecommendationCard
                key={recommendation.job_id}
                recommendation={recommendation}
                detailPath="/candidate/jobs"
              />
            ))}
          </div>
        )
      ) : null}
    </div>
  )
}