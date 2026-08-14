import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ClipboardCopy,
  Printer,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react'
import { getJobById } from '@/api/jobs'
import { generateInterviewQuestions } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { InterviewQuestionCard } from '@/features/recruiter/components/InterviewQuestionCard'
import type {
  GenerateInterviewQuestionsResponse,
  QuestionGenerationDifficulty,
} from '@/types/ai'
import type { Job } from '@/types/job'
import type { ParsedJob } from '@/types/ai'

const NUM_QUESTIONS_OPTIONS = [3, 5, 10, 15]

const DIFFICULTY_OPTIONS: { value: QuestionGenerationDifficulty; label: string }[] = [
  { value: 'easy', label: 'Easy' },
  { value: 'medium', label: 'Medium' },
  { value: 'hard', label: 'Hard' },
  { value: 'mixed', label: 'Mixed' },
]

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; notFound: boolean }
  | { kind: 'success'; job: Job }

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
  const [pageState, setPageState] = useState<PageState>({ kind: 'loading' })
  const [numQuestions, setNumQuestions] = useState(5)
  const [difficulty, setDifficulty] =
    useState<QuestionGenerationDifficulty>('medium')
  const [focusAreaInput, setFocusAreaInput] = useState('')
  const [focusAreas, setFocusAreas] = useState<string[]>([])
  const [generateState, setGenerateState] = useState<GenerateState>({
    kind: 'idle',
  })

  const load = useCallback(() => {
    if (!id) {
      setPageState({ kind: 'error', message: 'Job not found', notFound: true })
      return
    }
    setPageState({ kind: 'loading' })
    getJobById(id)
      .then((job) => setPageState({ kind: 'success', job }))
      .catch((err) => {
        const status = (err as Error & { response?: { status?: number } })
          .response?.status
        const notFound = status === 404
        setPageState({
          kind: 'error',
          message: notFound ? 'Job not found' : getFriendlyErrorMessage(err),
          notFound,
        })
      })
  }, [id])

  useEffect(() => {
    load()
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
    setGenerateState({ kind: 'loading' })

    try {
      const response = await generateInterviewQuestions({
        job: toParsedJob(pageState.job),
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
          {pageState.notFound ? '404' : 'Error'}
        </p>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight">
          {pageState.message}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {pageState.notFound
            ? 'The job you are looking for does not exist.'
            : 'Something went wrong while loading the job.'}
        </p>
        <div className="mt-6 flex items-center gap-3">
          {pageState.notFound ? (
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

  const { job } = pageState

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
        title="Bộ câu hỏi phỏng vấn AI"
        description={`Tạo câu hỏi phỏng vấn cho tin tuyển dụng "${job.title}" dựa trên yêu cầu công việc.`}
      />

      <form
        onSubmit={handleSubmit}
        className="mb-8 rounded-xl border bg-card/60 p-6"
      >
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="space-y-2">
            <p className="text-sm font-medium">Số lượng câu hỏi</p>
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
            <p className="text-sm font-medium">Trọng tâm (focus areas)</p>
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
            </p>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={copyQuestions}>
                <ClipboardCopy className="h-4 w-4" aria-hidden="true" />
                Copy câu hỏi
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
    </div>
  )
}
