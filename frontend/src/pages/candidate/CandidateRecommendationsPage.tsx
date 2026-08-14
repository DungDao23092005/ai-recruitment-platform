import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileUp, RefreshCw } from 'lucide-react'
import { getJobRecommendations } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
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
    <div className="container py-10">
      <PageHeader
        title="Gợi ý việc làm"
        description="Top jobs được AI gợi ý dựa trên kỹ năng và kinh nghiệm của bạn."
      />

      {state.kind === 'loading' ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 text-center">
          <Spinner size="lg" />
          <p className="text-sm text-muted-foreground">
            AI đang phân tích và đối sánh hồ sơ...
          </p>
        </div>
      ) : null}

      {state.kind === 'error' ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 text-center">
          <p className="max-w-md text-sm text-muted-foreground">
            {state.message}
          </p>
          <Button variant="outline" onClick={load}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Thử lại
          </Button>
        </div>
      ) : null}

      {state.kind === 'success' ? (
        state.recommendations.length === 0 ? (
          <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 text-center">
            <p className="max-w-md text-sm text-muted-foreground">
              Chưa có gợi ý việc làm phù hợp. Hãy tải lên CV PDF tại mục Hồ
              sơ để AI phân tích kỹ năng của bạn!
            </p>
            <Link to="/candidate/cv-upload">
              <Button>
                <FileUp className="h-4 w-4" aria-hidden="true" />
                Tải lên CV
              </Button>
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {state.recommendations.map((recommendation) => (
              <JobRecommendationCard
                key={recommendation.job_id}
                recommendation={recommendation}
              />
            ))}
          </div>
        )
      ) : null}
    </div>
  )
}