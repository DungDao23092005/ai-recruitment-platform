import { useCallback, useEffect, useState } from 'react'
import {
  ClipboardList,
  Lock,
  Pencil,
  RefreshCw,
  Star,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { EmptyState } from '@/components/ui/empty-state'
import { useAuth } from '@/contexts/AuthContext'
import {
  createInterviewEvaluation,
  deleteInterviewEvaluation,
  listApplicationEvaluations,
  updateInterviewEvaluation,
} from '@/api/applications'
import { getErrorStatus, getFriendlyErrorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/datetime'
import {
  EVALUATION_RECOMMENDATION_LABELS,
  type EvaluationRecommendation,
  type Interview,
  type InterviewEvaluation,
} from '@/types/application'

const RECOMMENDATION_OPTIONS: {
  value: EvaluationRecommendation | ''
  label: string
}[] = [
  { value: '', label: 'Không đưa ra đề xuất' },
  ...(
    Object.keys(EVALUATION_RECOMMENDATION_LABELS) as EvaluationRecommendation[]
  ).map((value) => ({ value, label: EVALUATION_RECOMMENDATION_LABELS[value] })),
]

const INTERVIEW_TYPE_LABELS: Record<Interview['interview_type'], string> = {
  technical: 'Chuyên môn',
  behavioral: 'Hành vi',
  hr: 'Nhân sự',
  case_study: 'Bài tập',
}

interface EvaluationFormValues {
  rating: number
  recommendation: EvaluationRecommendation | ''
  strengths: string
  weaknesses: string
  notes: string
}

const EMPTY_FORM: EvaluationFormValues = {
  rating: 5,
  recommendation: '',
  strengths: '',
  weaknesses: '',
  notes: '',
}

function RatingStars({ value }: { value: number }) {
  return (
    <span
      className="flex items-center gap-0.5"
      aria-label={`Đánh giá ${value}/5`}
    >
      {Array.from({ length: 5 }).map((_, index) => (
        <Star
          key={index}
          className={
            index < value
              ? 'h-3.5 w-3.5 fill-warning text-warning'
              : 'h-3.5 w-3.5 text-muted-foreground'
          }
          aria-hidden="true"
        />
      ))}
      <span className="ml-1 text-xs text-muted-foreground">{value}/5</span>
    </span>
  )
}

interface EvaluationFormProps {
  submitLabel: string
  submitting: boolean
  initial?: InterviewEvaluation
  onCancel: () => void
  onSubmit: (values: EvaluationFormValues) => void
}

function EvaluationForm({
  submitLabel,
  submitting,
  initial,
  onCancel,
  onSubmit,
}: EvaluationFormProps) {
  const [values, setValues] = useState<EvaluationFormValues>(
    initial
      ? {
          rating: initial.rating,
          recommendation: initial.recommendation ?? '',
          strengths: initial.strengths ?? '',
          weaknesses: initial.weaknesses ?? '',
          notes: initial.notes ?? '',
        }
      : EMPTY_FORM,
  )

  return (
    <form
      className="space-y-3 rounded-lg border bg-background p-3"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(values)
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Select
          id="evaluation-rating"
          name="rating"
          label="Điểm đánh giá"
          value={String(values.rating)}
          onChange={(e) =>
            setValues((prev) => ({ ...prev, rating: Number(e.target.value) }))
          }
        >
          {[1, 2, 3, 4, 5].map((score) => (
            <option key={score} value={score}>
              {score} / 5
            </option>
          ))}
        </Select>
        <Select
          id="evaluation-recommendation"
          name="recommendation"
          label="Đề xuất"
          value={values.recommendation}
          onChange={(e) =>
            setValues((prev) => ({
              ...prev,
              recommendation: e.target.value as EvaluationRecommendation | '',
            }))
          }
        >
          {RECOMMENDATION_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>

      <Textarea
        id="evaluation-strengths"
        name="strengths"
        label="Điểm mạnh"
        value={values.strengths}
        maxLength={1000}
        rows={2}
        onChange={(e) =>
          setValues((prev) => ({ ...prev, strengths: e.target.value }))
        }
      />
      <Textarea
        id="evaluation-weaknesses"
        name="weaknesses"
        label="Điểm cần cải thiện"
        value={values.weaknesses}
        maxLength={1000}
        rows={2}
        onChange={(e) =>
          setValues((prev) => ({ ...prev, weaknesses: e.target.value }))
        }
      />
      <Textarea
        id="evaluation-notes"
        name="notes"
        label="Ghi chú"
        value={values.notes}
        maxLength={2000}
        rows={2}
        onChange={(e) =>
          setValues((prev) => ({ ...prev, notes: e.target.value }))
        }
      />

      <div className="flex gap-2">
        <Button type="submit" size="sm" isLoading={submitting}>
          {submitLabel}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={submitting}
        >
          Hủy
        </Button>
      </div>
    </form>
  )
}

type EvaluationsState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; evaluations: InterviewEvaluation[] }

export interface InterviewEvaluationListProps {
  applicationId: string
  interviews: Interview[]
}

export function InterviewEvaluationList({
  applicationId,
  interviews,
}: InterviewEvaluationListProps) {
  const { currentUser } = useAuth()
  const [state, setState] = useState<EvaluationsState>({ kind: 'loading' })
  const [creatingFor, setCreatingFor] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    if (interviews.length === 0) {
      setState({ kind: 'success', evaluations: [] })
      return
    }
    let active = true
    setState({ kind: 'loading' })
    listApplicationEvaluations(applicationId)
      .then((evaluations) => {
        if (active) setState({ kind: 'success', evaluations })
      })
      .catch((err) => {
        if (active) {
          setState({
            kind: 'error',
            message:
              getErrorStatus(err) === 403
                ? 'Bạn không có quyền xem đánh giá phỏng vấn của đơn ứng tuyển này.'
                : getFriendlyErrorMessage(err),
          })
        }
      })
    return () => {
      active = false
    }
  }, [applicationId, interviews.length])

  useEffect(() => {
    return load()
  }, [load])

  const evaluations = state.kind === 'success' ? state.evaluations : []
  const byInterview = (interviewId: string) =>
    evaluations.filter((evaluation) => evaluation.interview_id === interviewId)
  const ownEvaluation = (interviewId: string) =>
    evaluations.find(
      (evaluation) =>
        evaluation.interview_id === interviewId &&
        evaluation.evaluator_id === currentUser?.id,
    )

  const canManage = (evaluation: InterviewEvaluation) =>
    currentUser?.role === 'admin' ||
    evaluation.evaluator_id === currentUser?.id

  const handleCreate = async (
    interviewId: string,
    values: EvaluationFormValues,
  ) => {
    setSubmitting(true)
    setError(null)
    try {
      const created = await createInterviewEvaluation(
        applicationId,
        interviewId,
        {
          rating: values.rating,
          strengths: values.strengths || null,
          weaknesses: values.weaknesses || null,
          recommendation: values.recommendation || null,
          notes: values.notes || null,
        },
      )
      setState((prev) =>
        prev.kind === 'success'
          ? { kind: 'success', evaluations: [...prev.evaluations, created] }
          : { kind: 'success', evaluations: [created] },
      )
      setCreatingFor(null)
    } catch (err) {
      setError(
        getErrorStatus(err) === 409
          ? 'Bạn đã đánh giá buổi phỏng vấn này. Hãy chỉnh sửa đánh giá hiện có.'
          : getErrorStatus(err) === 403
            ? 'Bạn không có quyền đánh giá buổi phỏng vấn này.'
            : getFriendlyErrorMessage(err),
      )
    } finally {
      setSubmitting(false)
    }
  }

  const handleUpdate = async (
    evaluation: InterviewEvaluation,
    values: EvaluationFormValues,
  ) => {
    setSubmitting(true)
    setError(null)
    try {
      const updated = await updateInterviewEvaluation(
        applicationId,
        evaluation.id,
        {
          rating: values.rating,
          strengths: values.strengths,
          weaknesses: values.weaknesses,
          recommendation: values.recommendation || null,
          notes: values.notes,
        },
      )
      setState((prev) =>
        prev.kind === 'success'
          ? {
              kind: 'success',
              evaluations: prev.evaluations.map((item) =>
                item.id === updated.id ? updated : item,
              ),
            }
          : prev,
      )
      setEditingId(null)
    } catch (err) {
      setError(
        getErrorStatus(err) === 403
          ? 'Chỉ người đánh giá hoặc quản trị viên mới có thể sửa đánh giá này.'
          : getFriendlyErrorMessage(err),
      )
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (evaluation: InterviewEvaluation) => {
    if (!window.confirm('Bạn có chắc chắn muốn xóa đánh giá này?')) return
    setSubmitting(true)
    setError(null)
    try {
      await deleteInterviewEvaluation(applicationId, evaluation.id)
      setState((prev) =>
        prev.kind === 'success'
          ? {
              kind: 'success',
              evaluations: prev.evaluations.filter(
                (item) => item.id !== evaluation.id,
              ),
            }
          : prev,
      )
    } catch (err) {
      setError(
        getErrorStatus(err) === 403
          ? 'Chỉ người đánh giá hoặc quản trị viên mới có thể xóa đánh giá này.'
          : getFriendlyErrorMessage(err),
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (interviews.length === 0) {
    return (
      <EmptyState
        icon={<ClipboardList className="h-6 w-6" aria-hidden="true" />}
        title="Chưa có buổi phỏng vấn"
        description="Cần có lịch phỏng vấn trước khi có thể đánh giá ứng viên."
      />
    )
  }

  return (
    <div className="space-y-4">
      <p className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        <Lock className="h-3.5 w-3.5" aria-hidden="true" />
        Đánh giá phỏng vấn là nội bộ, chỉ nhà tuyển dụng và quản trị viên xem được.
      </p>

      {error ? (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive">
          {error}
        </p>
      ) : null}

      {state.kind === 'loading' ? (
        <div className="flex items-center justify-center gap-3 py-8 text-muted-foreground">
          <Spinner size="md" />
          <span>Đang tải đánh giá...</span>
        </div>
      ) : state.kind === 'error' ? (
        <div className="space-y-4 py-4 text-center">
          <p role="alert" className="text-sm font-medium text-destructive">
            {state.message}
          </p>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Thử lại
          </Button>
        </div>
      ) : (
        <ul className="space-y-4">
          {interviews.map((interview) => {
            const interviewEvaluations = byInterview(interview.id)
            const mine = ownEvaluation(interview.id)
            return (
              <li
                key={interview.id}
                className="space-y-3 rounded-xl border bg-muted/20 px-4 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-foreground">
                      Phỏng vấn {INTERVIEW_TYPE_LABELS[interview.interview_type]}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(interview.scheduled_at)}
                    </p>
                  </div>
                  {!mine && creatingFor !== interview.id ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setCreatingFor(interview.id)
                        setEditingId(null)
                        setError(null)
                      }}
                    >
                      Thêm đánh giá
                    </Button>
                  ) : null}
                </div>

                {creatingFor === interview.id ? (
                  <EvaluationForm
                    submitLabel="Gửi đánh giá"
                    submitting={submitting}
                    onCancel={() => setCreatingFor(null)}
                    onSubmit={(values) => handleCreate(interview.id, values)}
                  />
                ) : null}

                {interviewEvaluations.length === 0 && creatingFor !== interview.id ? (
                  <p className="text-sm italic text-muted-foreground">
                    Chưa có đánh giá nào cho buổi phỏng vấn này.
                  </p>
                ) : null}

                {interviewEvaluations.map((evaluation) =>
                  editingId === evaluation.id ? (
                    <EvaluationForm
                      key={evaluation.id}
                      submitLabel="Lưu đánh giá"
                      submitting={submitting}
                      initial={evaluation}
                      onCancel={() => setEditingId(null)}
                      onSubmit={(values) => handleUpdate(evaluation, values)}
                    />
                  ) : (
                    <div
                      key={evaluation.id}
                      className="rounded-lg border bg-background px-3 py-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="neutral">
                            {evaluation.evaluator_id === currentUser?.id
                              ? 'Bạn'
                              : 'Đồng nghiệp'}
                          </Badge>
                          <RatingStars value={evaluation.rating} />
                          {evaluation.recommendation ? (
                            <Badge variant="info">
                              {
                                EVALUATION_RECOMMENDATION_LABELS[
                                  evaluation.recommendation
                                ]
                              }
                            </Badge>
                          ) : null}
                        </div>
                        {canManage(evaluation) ? (
                          <div className="flex items-center gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              aria-label="Sửa đánh giá"
                              onClick={() => {
                                setEditingId(evaluation.id)
                                setCreatingFor(null)
                                setError(null)
                              }}
                              disabled={submitting}
                            >
                              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-destructive hover:text-destructive"
                              aria-label="Xóa đánh giá"
                              onClick={() => handleDelete(evaluation)}
                              disabled={submitting}
                            >
                              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                            </Button>
                          </div>
                        ) : null}
                      </div>

                      <dl className="mt-2 space-y-1.5 text-sm">
                        {evaluation.strengths ? (
                          <div>
                            <dt className="font-medium text-foreground">
                              Điểm mạnh
                            </dt>
                            <dd className="whitespace-pre-wrap text-muted-foreground">
                              {evaluation.strengths}
                            </dd>
                          </div>
                        ) : null}
                        {evaluation.weaknesses ? (
                          <div>
                            <dt className="font-medium text-foreground">
                              Điểm cần cải thiện
                            </dt>
                            <dd className="whitespace-pre-wrap text-muted-foreground">
                              {evaluation.weaknesses}
                            </dd>
                          </div>
                        ) : null}
                        {evaluation.notes ? (
                          <div>
                            <dt className="font-medium text-foreground">
                              Ghi chú
                            </dt>
                            <dd className="whitespace-pre-wrap text-muted-foreground">
                              {evaluation.notes}
                            </dd>
                          </div>
                        ) : null}
                      </dl>

                      <p className="mt-2 text-xs text-muted-foreground">
                        {formatDateTime(evaluation.created_at)}
                        {evaluation.updated_at !== evaluation.created_at
                          ? ' · đã chỉnh sửa'
                          : ''}
                      </p>
                    </div>
                  ),
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
