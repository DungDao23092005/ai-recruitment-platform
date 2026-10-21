import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  AlertTriangle,
  Briefcase,
  ClipboardList,
  Clock,
  ListChecks,
  Lightbulb,
  ScrollText,
  Sparkles,
} from 'lucide-react'
import {
  getApplicationMatchExplanation,
  refreshApplicationMatchExplanation,
} from '@/api/applications'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Progress } from '@/components/ui/progress'
import { ScoreRing } from '@/components/ui/score-ring'
import { Skeleton } from '@/components/ui/skeleton'
import { AreasForInquiryCard } from '@/features/ai/components/AreasForInquiryCard'
import { EvidenceExcerptView } from '@/features/ai/components/EvidenceExcerptView'
import { ExperienceEvaluationList } from '@/features/ai/components/ExperienceEvaluationList'
import { SkillEvaluationList } from '@/features/ai/components/SkillEvaluationList'
import { cn } from '@/utils/cn'
import { formatDateTime } from '@/utils/datetime'
import { getErrorStatus, getFriendlyErrorMessage } from '@/utils/errors'
import type {
  ApplicationMatchExplanationResponse,
  CacheState,
  ScoreBreakdown,
  SummarySource,
} from '@/types/ai'

type BadgeVariant = NonNullable<BadgeProps['variant']>

const SOURCE_META: Record<
  SummarySource,
  { label: string; variant: BadgeVariant; description: string }
> = {
  ai_generated: {
    label: 'Tóm tắt do AI tạo',
    variant: 'ai-gradient',
    description:
      'Phần tóm tắt do mô hình AI tạo và không được đối chiếu nguyên văn với CV.',
  },
  deterministic: {
    label: 'Tóm tắt tự động',
    variant: 'neutral',
    description:
      'Phần tóm tắt được tạo cục bộ từ kết quả đối sánh, không sử dụng AI.',
  },
}

const CACHE_META: Record<
  CacheState,
  { label: string; variant: BadgeVariant }
> = {
  not_cached: { label: 'Mới tính cho lần xem này', variant: 'neutral' },
  cached: { label: 'Đã lưu trong bộ nhớ đệm', variant: 'info' },
  db_replay: { label: 'Khôi phục từ kết quả đã lưu', variant: 'info' },
}

const BREAKDOWN_FIELDS: { key: keyof ScoreBreakdown; label: string }[] = [
  { key: 'cosine_similarity', label: 'Độ tương đồng ngữ nghĩa' },
  { key: 'skill_coverage_score', label: 'Độ phủ kỹ năng bắt buộc' },
  { key: 'preferred_skill_coverage_score', label: 'Độ phủ kỹ năng ưu tiên' },
  { key: 'experience_match_score', label: 'Độ khớp kinh nghiệm' },
  { key: 'education_score', label: 'Độ khớp học vấn' },
  { key: 'project_score', label: 'Dẫn chứng kỹ năng dự án' },
]

type RefreshStatus =
  | 'idle'
  | 'refreshing'
  | 'cooldown'
  | 'error'
  | 'quota'
  | 'success'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; applicationId: string; message: string }
  | {
      kind: 'success'
      applicationId: string
      data: ApplicationMatchExplanationResponse
    }

type RefreshFailure =
  | { kind: 'cooldown'; retryAfter: number; message: string; keepKey: boolean }
  | { kind: 'quota'; message: string; keepKey: boolean }
  | { kind: 'error'; message: string; keepKey: boolean }

function toPercent(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value * 100)))
}

function toOverall(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
}

function getRetryAfterSeconds(error: unknown): number | null {
  if (typeof error !== 'object' || error === null) return null
  const response = (error as { response?: { headers?: Record<string, unknown> } })
    .response
  const headers = response?.headers
  if (!headers) return null
  const raw = headers['retry-after'] ?? headers['Retry-After']
  if (typeof raw !== 'string' && typeof raw !== 'number') return null
  const parsed = Number.parseInt(String(raw), 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

export function getExplanationErrorMessage(error: unknown): string {
  const status = getErrorStatus(error)
  if (status === 401) {
    return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  }
  if (status === 403) {
    return 'Bạn không có quyền xem giải thích đối sánh của ứng viên này.'
  }
  if (status === 404) {
    return 'Không tìm thấy đơn ứng tuyển hoặc ứng viên không thuộc công việc bạn quản lý.'
  }
  if (status === 503 || status === undefined) {
    return 'Không thể tải phân tích đối sánh. Vui lòng kiểm tra kết nối và thử lại.'
  }
  return getFriendlyErrorMessage(error)
}

function classifyRefreshFailure(error: unknown): RefreshFailure {
  const status = getErrorStatus(error)
  if (status === 409) {
    return {
      kind: 'cooldown',
      retryAfter: getRetryAfterSeconds(error) ?? 5,
      message:
        'Hệ thống đang xử lý một lượt phân tích khác cho ứng viên này. Vui lòng đợi trong giây lát.',
      keepKey: false,
    }
  }
  if (status === 429) {
    return {
      kind: 'quota',
      message:
        'Đã hết hạn mức phân tích AI trong kỳ này. Kết quả đối sánh hiện có vẫn được giữ nguyên.',
      keepKey: false,
    }
  }
  if (status === 403) {
    return {
      kind: 'error',
      message: 'Bạn không có quyền tạo phân tích AI cho ứng viên này.',
      keepKey: false,
    }
  }
  if (status === 404) {
    return {
      kind: 'error',
      message:
        'Không tìm thấy đơn ứng tuyển hoặc ứng viên không thuộc công việc bạn quản lý.',
      keepKey: false,
    }
  }
  if (status === 400 || status === 422) {
    return { kind: 'error', message: getFriendlyErrorMessage(error), keepKey: false }
  }
  if (status === 503) {
    return {
      kind: 'error',
      message:
        'Dịch vụ phân tích AI tạm thời không khả dụng. Kết quả hiện có vẫn được giữ nguyên; bạn có thể thử lại.',
      keepKey: true,
    }
  }
  return {
    kind: 'error',
    message:
      'Không thể kết nối tới máy chủ. Kết quả hiện có vẫn được giữ nguyên; bạn có thể thử lại.',
    keepKey: true,
  }
}

function SectionHeading({
  icon,
  children,
}: {
  icon: ReactNode
  children: ReactNode
}) {
  return (
    <h3 className="flex items-center gap-2 font-display text-base font-semibold text-foreground">
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-primary">
        {icon}
      </span>
      {children}
    </h3>
  )
}

export interface ApplicationMatchExplanationProps {
  applicationId: string
  className?: string
}

export function ApplicationMatchExplanation({
  applicationId,
  className,
}: ApplicationMatchExplanationProps) {
  const [loadState, setLoadState] = useState<LoadState>({ kind: 'loading' })
  const [reloadToken, setReloadToken] = useState(0)
  const [refreshStatus, setRefreshStatus] = useState<RefreshStatus>('idle')
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null)
  const [cooldownSeconds, setCooldownSeconds] = useState(0)

  const mountedRef = useRef(true)
  const requestSeqRef = useRef(0)
  const refreshKeyRef = useRef<string | null>(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    const seq = ++requestSeqRef.current
    setLoadState({ kind: 'loading' })
    setRefreshStatus('idle')
    setRefreshMessage(null)
    setCooldownSeconds(0)
    refreshKeyRef.current = null

    getApplicationMatchExplanation(applicationId)
      .then((data) => {
        if (!mountedRef.current || requestSeqRef.current !== seq) return
        setLoadState({ kind: 'success', applicationId, data })
      })
      .catch((error) => {
        if (!mountedRef.current || requestSeqRef.current !== seq) return
        setLoadState({
          kind: 'error',
          applicationId,
          message: getExplanationErrorMessage(error),
        })
      })

    return () => {
      requestSeqRef.current += 1
    }
  }, [applicationId, reloadToken])

  useEffect(() => {
    if (refreshStatus !== 'cooldown' || cooldownSeconds <= 0) return
    const timer = window.setTimeout(() => {
      setCooldownSeconds((seconds) => Math.max(0, seconds - 1))
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [refreshStatus, cooldownSeconds])

  useEffect(() => {
    if (refreshStatus !== 'cooldown' || cooldownSeconds > 0) return
    setRefreshStatus('idle')
    setRefreshMessage('Bạn có thể thử lại phân tích AI.')
  }, [refreshStatus, cooldownSeconds])

  const handleRefresh = useCallback(async () => {
    if (refreshStatus === 'refreshing' || refreshStatus === 'cooldown') return
    const key = refreshKeyRef.current ?? crypto.randomUUID()
    refreshKeyRef.current = key
    const seq = ++requestSeqRef.current
    setRefreshStatus('refreshing')
    setRefreshMessage(null)

    try {
      const data = await refreshApplicationMatchExplanation(applicationId, key)
      if (!mountedRef.current || requestSeqRef.current !== seq) return
      refreshKeyRef.current = null
      setLoadState({ kind: 'success', applicationId, data })
      setRefreshStatus('success')
      setRefreshMessage(
        'Đã cập nhật phân tích AI. Nội dung bên dưới đã được làm mới.',
      )
    } catch (error) {
      if (!mountedRef.current || requestSeqRef.current !== seq) return
      const failure = classifyRefreshFailure(error)
      if (!failure.keepKey) refreshKeyRef.current = null
      if (failure.kind === 'cooldown') {
        setCooldownSeconds(failure.retryAfter)
        setRefreshStatus('cooldown')
      } else if (failure.kind === 'quota') {
        setRefreshStatus('quota')
      } else {
        setRefreshStatus('error')
      }
      setRefreshMessage(failure.message)
    }
  }, [applicationId, refreshStatus])

  const currentData =
    loadState.kind === 'success' && loadState.applicationId === applicationId
      ? loadState.data
      : undefined
  const loadError =
    loadState.kind === 'error' && loadState.applicationId === applicationId
      ? loadState.message
      : null

  if (loadError) {
    return (
      <div className={cn('space-y-4', className)}>
        <ErrorBanner message={loadError} onRetry={() => setReloadToken((t) => t + 1)} />
      </div>
    )
  }

  if (!currentData) {
    return (
      <div className={cn('space-y-4', className)} role="status" aria-busy="true">
        <span className="sr-only">Đang tải phân tích đối sánh...</span>
        <div className="flex flex-wrap items-center gap-5 rounded-xl border bg-card p-5">
          <Skeleton className="h-[88px] w-[88px] rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-4 w-64" />
          </div>
        </div>
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-44 w-full rounded-xl" />
      </div>
    )
  }

  const overall = toOverall(currentData.overall_score)
  const sourceMeta = SOURCE_META[currentData.summary_source]
  const cacheMeta = CACHE_META[currentData.cache_state]
  const generatedAt = formatDateTime(currentData.generated_at)
  const refreshBusy = refreshStatus === 'refreshing'
  const refreshLocked = refreshBusy || refreshStatus === 'cooldown'
  const refreshLabel =
    refreshStatus === 'cooldown'
      ? `Thử lại sau ${cooldownSeconds}s`
      : currentData.summary_source === 'ai_generated'
        ? 'Tạo lại phân tích AI'
        : 'Tạo phân tích AI'
  const statusIsAlert = refreshStatus === 'error' || refreshStatus === 'quota'
  const statusClass =
    refreshStatus === 'error'
      ? 'border-destructive/30 bg-destructive/5 text-destructive'
      : refreshStatus === 'quota'
        ? 'border-warning/30 bg-warning/5 text-warning'
        : 'border-border bg-muted/40 text-muted-foreground'

  return (
    <div className={cn('space-y-6', className)}>
      <header className="rounded-xl border bg-card p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-4">
          <ScoreRing
            value={overall}
            size={88}
            strokeWidth={7}
            label={`Điểm đối sánh tổng thể ${overall} phần trăm`}
          />
          <div className="min-w-0 flex-1 space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Điểm đối sánh tổng thể
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={sourceMeta.variant} title={sourceMeta.description}>
                {sourceMeta.label}
              </Badge>
              <Badge variant={cacheMeta.variant}>{cacheMeta.label}</Badge>
            </div>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {generatedAt ? (
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  Cập nhật lúc {generatedAt}
                </span>
              ) : null}
              {currentData.model_version ? (
                <span>Mô hình: {currentData.model_version}</span>
              ) : null}
            </p>
          </div>
          <div className="sm:ml-auto">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshLocked}
              isLoading={refreshBusy}
              loadingText="Đang phân tích..."
            >
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              {refreshLabel}
            </Button>
          </div>
        </div>

        {refreshMessage ? (
          <p
            role={statusIsAlert ? 'alert' : 'status'}
            className={cn('mt-4 rounded-lg border px-3 py-2 text-sm', statusClass)}
          >
            {refreshMessage}
            {refreshStatus === 'cooldown' && cooldownSeconds > 0
              ? ` Còn ${cooldownSeconds} giây.`
              : ''}
          </p>
        ) : null}
      </header>

      <section className="space-y-3">
        <SectionHeading icon={<ScrollText className="h-4 w-4" aria-hidden="true" />}>
          Tóm tắt đánh giá
        </SectionHeading>
        <p className="text-sm leading-relaxed text-foreground/90">
          {currentData.summary}
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading icon={<ClipboardList className="h-4 w-4" aria-hidden="true" />}>
          Chi tiết điểm số
        </SectionHeading>
        <div className="space-y-3">
          {BREAKDOWN_FIELDS.map((field) => {
            const raw = currentData.score_breakdown[field.key]
            const percent = toPercent(raw)
            return (
              <div key={field.key}>
                <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                  <span className="text-muted-foreground">{field.label}</span>
                  <span className="font-medium">{percent}%</span>
                </div>
                <Progress
                  value={percent}
                  aria-label={`${field.label}: ${percent}%`}
                />
              </div>
            )
          })}
        </div>
      </section>

      {currentData.key_strengths.length > 0 ? (
        <section className="space-y-3">
          <SectionHeading icon={<Lightbulb className="h-4 w-4" aria-hidden="true" />}>
            Điểm mạnh nổi bật
          </SectionHeading>
          <ul className="space-y-2">
            {currentData.key_strengths.map((strength, index) => (
              <li
                key={`strength-${index}`}
                className="flex items-start gap-2.5 text-sm leading-relaxed text-foreground"
              >
                <Lightbulb
                  className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                  aria-hidden="true"
                />
                <span className="min-w-0 break-words">{strength}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="space-y-3">
        <SectionHeading icon={<ListChecks className="h-4 w-4" aria-hidden="true" />}>
          Đối soát kỹ năng
        </SectionHeading>
        <SkillEvaluationList evaluations={currentData.skill_evaluations} />
      </section>

      <section className="space-y-3">
        <SectionHeading icon={<Briefcase className="h-4 w-4" aria-hidden="true" />}>
          Kinh nghiệm liên quan
        </SectionHeading>
        <ExperienceEvaluationList
          evaluations={currentData.experience_evaluations}
        />
      </section>

      <AreasForInquiryCard areas={currentData.areas_for_inquiry} />

      {currentData.evidence.length > 0 ? (
        <details className="rounded-xl border bg-card p-4">
          <summary className="cursor-pointer text-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
            Tất cả dẫn chứng từ CV ({currentData.evidence.length})
          </summary>
          <div className="mt-3 space-y-2">
            {currentData.evidence.map((excerpt, index) => (
              <EvidenceExcerptView key={`evidence-${index}`} excerpt={excerpt} />
            ))}
          </div>
        </details>
      ) : null}

      {currentData.data_limitations.length > 0 ? (
        <section className="space-y-3">
          <SectionHeading icon={<AlertTriangle className="h-4 w-4" aria-hidden="true" />}>
            Lưu ý về dữ liệu
          </SectionHeading>
          <ul className="space-y-2 rounded-xl border border-warning/30 bg-warning/5 px-4 py-3">
            {currentData.data_limitations.map((limitation, index) => (
              <li
                key={`limitation-${index}`}
                className="flex items-start gap-2.5 text-sm leading-relaxed text-foreground"
              >
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                  aria-hidden="true"
                />
                <span className="min-w-0 break-words">{limitation}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
