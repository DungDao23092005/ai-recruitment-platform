import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, RefreshCw, UserRoundSearch } from 'lucide-react'
import { getMyJobById } from '@/api/jobs'
import { getCandidateRecommendations } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
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
      setState({
        kind: 'error',
        message: 'Không tìm thấy tin tuyển dụng',
        notFound: true,
      })
      return
    }

    setState({ kind: 'loading' })

    Promise.all([getMyJobById(id), getCandidateRecommendations(id, DEFAULT_LIMIT)])
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
          message: notFound
            ? 'Không tìm thấy tin tuyển dụng'
            : getFriendlyErrorMessage(err),
          notFound,
        })
      })
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  if (state.kind === 'loading') {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-1/2" />
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-64 w-full" />
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
              : 'Đã xảy ra lỗi khi tải danh sách ứng viên gợi ý.'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {state.notFound ? (
            <Link to="/recruiter/jobs">
              <Button variant="outline">Quay lại tin tuyển dụng</Button>
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
    <div className="space-y-6">
      <Link to="/recruiter/jobs">
        <Button variant="ghost" size="sm">
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Quay lại tin tuyển dụng
        </Button>
      </Link>

      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Ứng viên phù hợp cho vị trí"
        description={`Top ứng viên được AI gợi ý cho tin tuyển dụng "${job.title}".`}
      />

      {recommendations.length === 0 ? (
        <EmptyState
          icon={<UserRoundSearch className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có ứng viên gợi ý"
          description="Chưa tìm thấy ứng viên phù hợp với yêu cầu của tin tuyển dụng này."
        />
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