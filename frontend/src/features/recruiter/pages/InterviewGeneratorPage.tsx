import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  ChevronLeft,
  ClipboardCopy,
  Printer,
  RefreshCw,
  Sparkles,
  X,
  AlertCircle,
  UserCheck,
} from 'lucide-react'
import { getMyJobById } from '@/api/jobs'
import { getApplicationDetail } from '@/api/applications'
import { getApplicationMatch } from '@/api/applications'
import { generateInterviewQuestions } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { InterviewQuestionCard } from '@/features/recruiter/components/InterviewQuestionCard'
import type {
  GenerateInterviewQuestionsResponse,
  QuestionGenerationDifficulty,
  MatchResult,
  ParsedResume,
} from '@/types/ai'
import type { Job } from '@/types/job'
import type { ParsedJob } from '@/types/ai'
import type { ApplicationDetail } from '@/types/application'

const NUM_QUESTIONS_OPTIONS = [3, 5, 10, 15]

const DIFFICULTY_OPTIONS: { value: QuestionGenerationDifficulty; label: string }[] = [
  { value: 'easy', label: 'Dễ' },
  { value: 'medium', label: 'Trung bình' },
  { value: 'hard', label: 'Khó' },
  { value: 'mixed', label: 'Kết hợp' },
]

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; notFound: boolean }
  | { kind: 'success'; job: Job; application?: ApplicationDetail | null; match?: MatchResult | null; personalizedError?: string }

type GenerateState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string; config: GenerateConfig }
  | { kind: 'success'; response: GenerateInterviewQuestionsResponse }

interface GenerateConfig {
  numQuestions: number
  difficulty: QuestionGenerationDifficulty
  focusAreas: string[]
}

function toParsedJob(job: Job): ParsedJob {
  return {
    title: job.title,
    summary: job.description,
    required_skills: [],
    preferred_skills: [],
    minimum_years_experience: null,
    education_level: null,
  }
}

function formatQuestionsForCopy(
  response: GenerateInterviewQuestionsResponse,
): string {
  const lines = response.questions.map((question, index) => {
    const points = question.sample_answer_points
      .map((point) => `  - ${point}`)
      .join('\n')
    return (
      `${index + 1}. [${question.category} / ${question.difficulty}] ${question.question}\n` +
      `   Kỹ năng: ${question.target_skill_or_topic}\n` +
      `   Tiêu chí đánh giá: ${question.evaluation_criteria}\n` +
      `   Gợi ý trả lời:\n${points}`
    )
  })
  return (
    `Bộ câu hỏi phỏng vấn - ${response.job_title}\n\n` + lines.join('\n\n')
  )
}

export function InterviewGeneratorPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  const applicationId = searchParams.get('applicationId')

  const [pageState, setPageState] = useState<PageState>({ kind: 'loading' })
  const [numQuestions, setNumQuestions] = useState(5)
  const [difficulty, setDifficulty] =
    useState<QuestionGenerationDifficulty>('medium')
  const [focusAreaInput, setFocusAreaInput] = useState('')
  const [focusAreas, setFocusAreas] = useState<string[]>([])
  const [generateState, setGenerateState] = useState<GenerateState>({
    kind: 'idle',
  })

  const load = useCallback(async () => {
    if (!id) {
      setPageState({
        kind: 'error',
        message: 'Không tìm thấy tin tuyển dụng',
        notFound: true,
      })
      return
    }
    setPageState({ kind: 'loading' })

    try {
      // 1. Always fetch job first (required context)
      const job = await getMyJobById(id)
      if (!active) return

      if (!applicationId) {
        // Generic mode: only job
        if (!active) return
        setPageState({ kind: 'success', job })
        return
      }

      // 2. Personalized mode: fetch application and match
      // Fetch application first
      let application: ApplicationDetail | null = null
      try {
        application = await getApplicationDetail(applicationId)
      } catch (err) {
        const status = (err as Error & { response?: { status?: number } }).response?.status
        if (status === 403 || status === 404) {
          // Application not found or unauthorized -> fallback to generic mode with warning
          if (!active) return
          setPageState({
            kind: 'success',
            job,
            application: null,
            match: null,
            personalizedError: 'Không thể tải hồ sơ ứng viên. Đang chuyển sang chế độ chung.',
          })
          return
        }
        throw err // Re-throw unexpected errors
      }

      if (!active) return

      // 3. Fetch match (optional, non-blocking)
      let match: MatchResult | null = null
      try {
        match = await getApplicationMatch(applicationId)
      } catch {
        match = null // Match fetch failed, continue without it
      }

      if (!active) return

      setPageState({ kind: 'success', job, application, match })
    } catch (err) {
      if (!active) return
      const status = (err as Error & { response?: { status?: number } }).response?.status
      const notFound = status === 404
      setPageState({
        kind: 'error',
        message: notFound
          ? 'Không tìm thấy tin tuyển dụng'
          : getFriendlyErrorMessage(err),
        notFound,
      })
    }
  }, [id, applicationId])

  // Track active state for async operations
  let active = true
  useEffect(() => {
    active = true
    load()
    return () => {
      active = false
    }
  }, [load])

  const addFocusArea = () => {
    const trimmed = focusAreaInput.trim()
    if (!trimmed) {
      return
    }
    if (!focusAreas.includes(trimmed)) {
      setFocusAreas((prev) => [...prev, trimmed])
    }
    setFocusAreaInput('')
  }

  const handleFocusAreaKeyDown = (
    e: React.KeyboardEvent<HTMLInputElement>,
  ) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addFocusArea()
    }
  }

  const removeFocusArea = (area: string) => {
    setFocusAreas((prev) => prev.filter((item) => item !== area))
  }

  const handleGenerate = async (config: GenerateConfig) => {
    if (pageState.kind !== 'success') {
      return
    }
    if (generateState.kind === 'loading') {
      return
    }
    setGenerateState({ kind: 'loading' })

    try {
      const job = pageState.job
      const application = pageState.application
      const match = pageState.match

      let candidate: ParsedResume | null = null
      if (application?.resume?.parsed_data) {
        candidate = application.resume.parsed_data
      }

      const response = await generateInterviewQuestions({
        job: toParsedJob(job),
        candidate: candidate ?? null,
        match_result: match ?? null,
        num_questions: config.numQuestions,
        difficulty: config.difficulty,
        focus_areas: config.focusAreas,
      })
      setGenerateState({ kind: 'success', response })
    } catch (err) {
      setGenerateState({
        kind: 'error',
        message: getFriendlyErrorMessage(err),
        config,
      })
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const config: GenerateConfig = {
      numQuestions,
      difficulty,
      focusAreas,
    }
    void handleGenerate(config)
  }

  const retry = () => {
    if (generateState.kind === 'error') {
      void handleGenerate(generateState.config)
    }
  }

  const copyQuestions = () => {
    if (generateState.kind !== 'success') {
      return
    }
    void navigator.clipboard.writeText(
      formatQuestionsForCopy(generateState.response),
    )
  }

  if (pageState.kind === 'loading') {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (pageState.kind === 'error') {
    return (
      <div className="container flex min-h-[50vh] flex-col items-center justify-center py-10 text-center">
        <p className="text-5xl font-bold text-primary">
          {pageState.notFound ? '404' : 'Lỗi'}
        </p>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight">
          {pageState.message}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {pageState.notFound
            ? 'Tin tuyển dụng bạn tìm kiếm không tồn tại.'
            : 'Đã xảy ra lỗi khi tải tin tuyển dụng.'}
        </p>
        <div className="mt-6 flex items-center gap-3">
          {pageState.notFound ? (
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

  const { job, application, match, personalizedError } = pageState

  const isPersonalized = !!applicationId && !personalizedError
  const candidateName = application?.candidate?.full_name || 'ứng viên này'
  const hasResume = !!application?.resume?.parsed_data
  const hasMatch = !!match
  const applicationError = personalizedError

  return (
    <div className="container py-10">
      <div className="mb-6 flex items-center gap-2">
        <Link to="/recruiter/jobs">
          <Button variant="ghost" size="sm">
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            Quay lại tin tuyển dụng
          </Button>
        </Link>
      </div>

      <PageHeader
        title="Bộ câu hỏi phỏng vấn AI"
        description={
          isPersonalized
            ? `Tạo câu hỏi phỏng vấn cá nhân hóa cho "${job.title}" dựa trên hồ sơ của ${candidateName}.`
            : `Tạo câu hỏi phỏng vấn cho tin tuyển dụng "${job.title}" dựa trên yêu cầu công việc.`
        }
      />

      {isPersonalized && (
        <div className="mb-6">
          <Card className="border-primary/30 bg-primary/5">
            <CardHeader>
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <UserCheck className="h-4 w-4" aria-hidden="true" />
                </div>
                <div>
                  <CardTitle className="text-base font-semibold">
                    Chế độ cá nhân hóa đang hoạt động
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Đang tạo câu hỏi cho <span className="font-medium">{candidateName}</span>
                    {' '}
                    {hasResume && hasMatch ? (
                      <>
                        (có CV và điểm khớp)
                      </>
                    ) : hasResume ? (
                      <>
                        (có CV, chưa có điểm khớp)
                      </>
                    ) : hasMatch ? (
                      <>
                        (có điểm khớp, chưa có CV)
                      </>
                    ) : (
                      <>
                        (chưa có CV và điểm khớp)
                      </>
                    )}
                  </p>
                </div>
              </div>
            </CardHeader>
          </Card>
        </div>
      )}

      {applicationError && (
        <ErrorBanner
          message={applicationError}
          onRetry={load}
        />
      )}

      <form
        onSubmit={handleSubmit}
        className="mb-8 rounded-xl border bg-card/60 p-6"
      >
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="space-y-2">
            <p className="text-sm font-medium">Số câu hỏi</p>
            <div className="flex flex-wrap gap-2">
              {NUM_QUESTIONS_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setNumQuestions(option)}
                  aria-pressed={numQuestions === option}
                  className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                    numQuestions === option
                      ? 'ai-gradient border-transparent text-white'
                      : 'bg-background text-muted-foreground hover:bg-accent'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">Độ khó</p>
            <div className="flex flex-wrap gap-2">
              {DIFFICULTY_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setDifficulty(option.value)}
                  aria-pressed={difficulty === option.value}
                  className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                    difficulty === option.value
                      ? 'ai-gradient border-transparent text-white'
                      : 'bg-background text-muted-foreground hover:bg-accent'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">Chủ đề tập trung</p>
            <div className="flex items-center gap-2">
              <Input
                name="focus-area"
                value={focusAreaInput}
                onChange={(e) => setFocusAreaInput(e.target.value)}
                onKeyDown={handleFocusAreaKeyDown}
                placeholder="Ví dụ: Performance testing"
                aria-label="Thêm trọng tâm"
              />
              <Button
                type="button"
                variant="outline"
                onClick={addFocusArea}
                disabled={!focusAreaInput.trim()}
              >
                Thêm
              </Button>
            </div>
            {focusAreas.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {focusAreas.map((area) => (
                  <span
                    key={area}
                    className="inline-flex items-center gap-1 rounded-full border bg-background px-2.5 py-0.5 text-xs"
                  >
                    {area}
                    <button
                      type="button"
                      onClick={() => removeFocusArea(area)}
                      aria-label={`Xóa trọng tâm ${area}`}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <div className="mt-6 flex justify-end">
          <Button
            type="submit"
            disabled={generateState.kind === 'loading'}
            isLoading={generateState.kind === 'loading'}
            loadingText="Đang tạo..."
          >
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            Tạo bộ câu hỏi
          </Button>
        </div>
      </form>

      {generateState.kind === 'error' ? (
        <div className="mb-8 flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
          <AlertCircle className="h-4 w-4 text-destructive shrink-0" aria-hidden="true" />
          <p role="alert" className="flex-1 text-sm text-destructive">
            {generateState.message}
          </p>
          <Button variant="outline" size="sm" onClick={retry}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Thử lại
          </Button>
        </div>
      ) : null}

      {generateState.kind === 'success' ? (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Đã tạo {generateState.response.total_questions} câu hỏi cho{' '}
              <span className="font-medium text-foreground">
                {generateState.response.job_title}
              </span>
              {isPersonalized && (
                <span className="ml-2 text-sm text-primary">
                  (cá nhân hóa cho {candidateName})
                </span>
              )}
            </p>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={copyQuestions}>
                <ClipboardCopy className="h-4 w-4" aria-hidden="true" />
                Sao chép câu hỏi
              </Button>
              <Button variant="outline" size="sm" onClick={() => window.print()}>
                <Printer className="h-4 w-4" aria-hidden="true" />
                In / Xuất PDF
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {generateState.response.questions.map((question, index) => (
              <InterviewQuestionCard
                key={`${index}-${question.question}`}
                index={index}
                question={question}
              />
            ))}
          </div>
        </div>
      ) : null}

      {/* Personalized mode info when no questions generated yet */}
      {isPersonalized && generateState.kind === 'idle' && (
        <Card className="border-info/30 bg-info/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-info" aria-hidden="true" />
              Tạo câu hỏi cá nhân hóa
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>
              AI sẽ tạo câu hỏi dựa trên:
              <ul className="mt-1 list-disc list-inside space-y-1 text-muted-foreground">
                <li>Yêu cầu công việc: <span className="font-medium">{job.title}</span></li>
                <li>Hồ sơ ứng viên: <span className="font-medium">{candidateName}</span></li>
                {hasResume && <li>CV đã phân tích: <span className="font-medium">Có</span></li>}
                {hasMatch && <li>Điểm khớp AI: <span className="font-medium">Có</span></li>}
                {!hasResume && <li className="text-warning">Chưa có CV được phân tích</li>}
                {!hasMatch && <li className="text-warning">Chưa có điểm khớp AI</li>}
              </ul>
            </p>
            <p className="text-xs text-muted-foreground">
              Câu hỏi sẽ được tạo khi bạn nhấn nút "Tạo bộ câu hỏi" ở trên.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Missing resume/match warning in personalized mode */}
      {isPersonalized && generateState.kind === 'idle' && (!hasResume || !hasMatch) && (
        <ErrorBanner
          message={
            !hasResume && !hasMatch
              ? 'Ứng viên này chưa có CV được phân tích và chưa có điểm khớp AI. Câu hỏi sẽ chỉ dựa trên mô tả công việc.'
              : !hasResume
              ? 'Ứng viên này chưa có CV được phân tích. Câu hỏi sẽ chỉ dựa trên mô tả công việc và điểm khớp (nếu có).'
              : 'Ứng viên này chưa có điểm khớp AI. Câu hỏi sẽ chỉ dựa trên mô tả công việc và CV (nếu có).'
          }
        />
      )}
    </div>
  )
}