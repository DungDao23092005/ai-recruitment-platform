import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  CalendarClock,
  ClipboardList,
  FileText,
  Lock,
  MapPin,
  Send,
  Star,
  Trash2,
  UserRound,
  Video,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Modal } from '@/components/ui/modal'
import { Skeleton } from '@/components/ui/skeleton'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/contexts/AuthContext'
import {
  createWorkspaceInterviewEvaluation,
  deleteWorkspaceInterviewEvaluation,
  getInterviewerApplication,
  listMyAssignedInterviews,
  listWorkspaceInterviewEvaluations,
  submitWorkspaceInterviewEvaluation,
  updateWorkspaceInterviewEvaluation,
} from '@/api/interviews'
import {
  EVALUATION_RECOMMENDATION_LABELS,
  type AssignedInterview,
  type EvaluationRecommendation,
  type InterviewEvaluation,
  type InterviewerApplication,
} from '@/types/application'
import { formatDateTime } from '@/utils/datetime'
import { getFriendlyErrorMessage } from '@/utils/errors'

const INTERVIEW_TYPE_LABELS: Record<string, string> = {
  technical: 'Kỹ thuật',
  behavioral: 'Hành vi',
  hr: 'Nhân sự',
  case_study: 'Tình huống',
}

const INTERVIEW_STATUS_LABELS: Record<string, string> = {
  scheduled: 'Đã lên lịch',
  candidate_confirmed: 'Ứng viên đã xác nhận',
  candidate_declined: 'Ứng viên từ chối',
  completed: 'Đã hoàn thành',
  cancelled: 'Đã hủy',
}

const RECOMMENDATION_OPTIONS: {
  value: EvaluationRecommendation | ''
  label: string
}[] = [
  { value: '', label: 'Không đưa ra đề xuất' },
  ...(
    Object.keys(EVALUATION_RECOMMENDATION_LABELS) as EvaluationRecommendation[]
  ).map((value) => ({ value, label: EVALUATION_RECOMMENDATION_LABELS[value] })),
]

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

export function MyInterviewsPage() {
  const { currentUser } = useAuth()
  const [interviews, setInterviews] = useState<AssignedInterview[]>([])
  const [selectedInterview, setSelectedInterview] =
    useState<AssignedInterview | null>(null)
  const [application, setApplication] =
    useState<InterviewerApplication | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isApplicationLoading, setIsApplicationLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [evaluations, setEvaluations] = useState<InterviewEvaluation[]>([])
  const [isEvaluationsLoading, setIsEvaluationsLoading] = useState(false)
  const [evaluationsError, setEvaluationsError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [submittingEvaluation, setSubmittingEvaluation] = useState(false)
  const [isConfirmSubmitOpen, setIsConfirmSubmitOpen] = useState(false)
  const [formValues, setFormValues] = useState<EvaluationFormValues>(EMPTY_FORM)

  const loadInterviews = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const items = await listMyAssignedInterviews()
      setInterviews(items)
      setSelectedInterview((current) => {
        if (current) {
          return items.find((item) => item.id === current.id) ?? null
        }
        return items[0] ?? null
      })
    } catch (loadError) {
      setError(getFriendlyErrorMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadInterviews()
  }, [loadInterviews])

  const loadApplication = useCallback(async (interviewId: string) => {
    setIsApplicationLoading(true)
    setApplication(null)
    try {
      const data = await getInterviewerApplication(interviewId)
      setApplication(data)
    } catch (loadError) {
      setError(getFriendlyErrorMessage(loadError))
    } finally {
      setIsApplicationLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedInterview) {
      void loadApplication(selectedInterview.id)
    } else {
      setApplication(null)
    }
  }, [loadApplication, selectedInterview])

  const loadEvaluations = useCallback(async (interviewId: string) => {
    setIsEvaluationsLoading(true)
    setEvaluationsError(null)
    setActionError(null)
    try {
      const data = await listWorkspaceInterviewEvaluations(interviewId)
      setEvaluations(data)
    } catch (loadErr) {
      setEvaluationsError(getFriendlyErrorMessage(loadErr))
    } finally {
      setIsEvaluationsLoading(false)
    }
  }, [])

  useEffect(() => {
    setIsConfirmSubmitOpen(false)
    if (selectedInterview) {
      void loadEvaluations(selectedInterview.id)
    } else {
      setEvaluations([])
    }
  }, [loadEvaluations, selectedInterview])

  const myEvaluation = evaluations.find(
    (e) => e.evaluator_id === currentUser?.id,
  )
  const otherEvaluations = evaluations.filter(
    (e) => e.evaluator_id !== currentUser?.id,
  )

  useEffect(() => {
    if (myEvaluation) {
      setFormValues({
        rating: myEvaluation.rating,
        recommendation: myEvaluation.recommendation ?? '',
        strengths: myEvaluation.strengths ?? '',
        weaknesses: myEvaluation.weaknesses ?? '',
        notes: myEvaluation.notes ?? '',
      })
    } else {
      setFormValues(EMPTY_FORM)
    }
  }, [myEvaluation])

  const handleSaveDraft = async () => {
    if (!selectedInterview) return
    setSubmittingEvaluation(true)
    setActionError(null)
    try {
      if (myEvaluation) {
        const updated = await updateWorkspaceInterviewEvaluation(
          selectedInterview.id,
          myEvaluation.id,
          {
            rating: formValues.rating,
            recommendation: formValues.recommendation || null,
            strengths: formValues.strengths || null,
            weaknesses: formValues.weaknesses || null,
            notes: formValues.notes || null,
          },
        )
        setEvaluations((prev) =>
          prev.map((e) => (e.id === updated.id ? updated : e)),
        )
      } else {
        const created = await createWorkspaceInterviewEvaluation(
          selectedInterview.id,
          {
            rating: formValues.rating,
            recommendation: formValues.recommendation || null,
            strengths: formValues.strengths || null,
            weaknesses: formValues.weaknesses || null,
            notes: formValues.notes || null,
          },
        )
        setEvaluations((prev) => [...prev, created])
      }
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setSubmittingEvaluation(false)
    }
  }

  const handleOpenConfirmSubmit = () => {
    setActionError(null)
    setIsConfirmSubmitOpen(true)
  }

  const handleCloseConfirmSubmit = () => {
    if (submittingEvaluation) return
    setIsConfirmSubmitOpen(false)
  }

  const handleConfirmSubmit = async () => {
    if (!selectedInterview || submittingEvaluation) return
    setSubmittingEvaluation(true)
    setActionError(null)
    try {
      let evaluationId = myEvaluation?.id
      if (!evaluationId) {
        const created = await createWorkspaceInterviewEvaluation(
          selectedInterview.id,
          {
            rating: formValues.rating,
            recommendation: formValues.recommendation || null,
            strengths: formValues.strengths || null,
            weaknesses: formValues.weaknesses || null,
            notes: formValues.notes || null,
          },
        )
        evaluationId = created.id
      } else {
        await updateWorkspaceInterviewEvaluation(
          selectedInterview.id,
          evaluationId,
          {
            rating: formValues.rating,
            recommendation: formValues.recommendation || null,
            strengths: formValues.strengths || null,
            weaknesses: formValues.weaknesses || null,
            notes: formValues.notes || null,
          },
        )
      }
      await submitWorkspaceInterviewEvaluation(
        selectedInterview.id,
        evaluationId,
      )
      await loadEvaluations(selectedInterview.id)
      setIsConfirmSubmitOpen(false)
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setSubmittingEvaluation(false)
    }
  }

  const handleDeleteDraft = async () => {
    if (!selectedInterview || !myEvaluation) return
    if (!window.confirm('Bạn có chắc chắn muốn xóa bản nháp đánh giá này?')) {
      return
    }
    setSubmittingEvaluation(true)
    setActionError(null)
    try {
      await deleteWorkspaceInterviewEvaluation(
        selectedInterview.id,
        myEvaluation.id,
      )
      setEvaluations((prev) => prev.filter((e) => e.id !== myEvaluation.id))
      setFormValues(EMPTY_FORM)
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setSubmittingEvaluation(false)
    }
  }

  const resume = application?.resume?.parsed_data

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Không gian làm việc"
        title="Lịch phỏng vấn của tôi"
        description="Chỉ các buổi phỏng vấn được phân công cho bạn mới hiển thị tại đây."
      />

      {error ? (
        <ErrorBanner message={error} onRetry={() => void loadInterviews()} />
      ) : null}

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : interviews.length === 0 ? (
        <EmptyState
          icon={<CalendarClock className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có buổi phỏng vấn nào"
          description="Khi nhà tuyển dụng phân công bạn vào một buổi phỏng vấn, lịch sẽ xuất hiện tại đây."
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_26rem]">
          <div className="space-y-3">
            {interviews.map((interview) => {
              const isSelected = selectedInterview?.id === interview.id
              return (
                <button
                  key={interview.id}
                  type="button"
                  onClick={() => setSelectedInterview(interview)}
                  className={`w-full rounded-lg border p-4 text-left transition-colors ${
                    isSelected
                      ? 'border-primary bg-primary/5'
                      : 'bg-card hover:bg-accent/50'
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-foreground">
                        {interview.job_title}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {interview.candidate_name ?? 'Ứng viên'}
                      </p>
                    </div>
                    <Badge variant="outline-ai">
                      {INTERVIEW_STATUS_LABELS[interview.status] ??
                        interview.status}
                    </Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <CalendarClock
                        className="h-4 w-4"
                        aria-hidden="true"
                      />
                      {formatDateTime(interview.scheduled_at)}
                    </span>
                    <span>
                      {INTERVIEW_TYPE_LABELS[interview.interview_type] ??
                        interview.interview_type}
                    </span>
                    <span>{interview.duration_minutes} phút</span>
                    {interview.location ? (
                      <span className="inline-flex items-center gap-1.5">
                        <MapPin className="h-4 w-4" aria-hidden="true" />
                        {interview.location}
                      </span>
                    ) : null}
                  </div>
                </button>
              )
            })}
          </div>

          <div className="space-y-6">
            <Card className="h-fit">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
                  Hồ sơ ứng viên
                </CardTitle>
                <CardDescription>
                  Thông tin liên hệ trực tiếp đã được ẩn để bảo vệ quyền riêng tư.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {isApplicationLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-20 w-full" />
                    <Skeleton className="h-20 w-full" />
                  </div>
                ) : !selectedInterview ? (
                  <p className="text-sm text-muted-foreground">
                    Chọn một buổi phỏng vấn để xem hồ sơ.
                  </p>
                ) : !application ? (
                  <p className="text-sm text-muted-foreground">
                    Không thể tải hồ sơ ứng viên.
                  </p>
                ) : (
                  <>
                    <div>
                      <p className="flex items-center gap-2 font-medium text-foreground">
                        <UserRound className="h-4 w-4" aria-hidden="true" />
                        {application.candidate?.full_name ?? 'Ứng viên'}
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {application.candidate?.title ?? 'Chưa cập nhật chức danh'}
                      </p>
                      <div className="mt-2 space-y-1 text-sm text-muted-foreground">
                        <p>{application.candidate?.email ?? 'Email đã ẩn'}</p>
                        <p>{application.candidate?.phone ?? 'Số điện thoại đã ẩn'}</p>
                      </div>
                    </div>

                    {selectedInterview.meeting_url ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          window.open(
                            selectedInterview.meeting_url ?? '',
                            '_blank',
                            'noopener,noreferrer',
                          )
                        }
                      >
                        <Video className="mr-1.5 h-4 w-4" aria-hidden="true" />
                        Mở phòng họp
                      </Button>
                    ) : null}

                    <div>
                      <p className="text-sm font-semibold text-foreground">
                        {application.job_title}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {application.company_name ?? ''}
                      </p>
                    </div>

                    {resume ? (
                      <div className="space-y-4">
                        {resume.summary ? (
                          <p className="text-sm text-muted-foreground">
                            {resume.summary}
                          </p>
                        ) : null}
                        {resume.skills.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5">
                            {resume.skills.map((skill) => (
                              <Badge key={skill} variant="neutral">
                                {skill}
                              </Badge>
                            ))}
                          </div>
                        ) : null}
                        {resume.experiences.length > 0 ? (
                          <div>
                            <p className="mb-2 text-sm font-medium text-foreground">
                              Kinh nghiệm
                            </p>
                            <ul className="space-y-2 text-sm text-muted-foreground">
                              {resume.experiences
                                .slice(0, 3)
                                .map((experience, index) => (
                                  <li key={index}>
                                    <span className="font-medium text-foreground">
                                      {experience.position ?? 'Vị trí'}
                                    </span>
                                    {experience.company
                                      ? ` · ${experience.company}`
                                      : ''}
                                  </li>
                                ))}
                            </ul>
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        Ứng viên chưa có CV đã phân tích.
                      </p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>

            {selectedInterview ? (
              <Card className="h-fit">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                      <ClipboardList className="h-5 w-5 text-primary" aria-hidden="true" />
                      Phiếu đánh giá phỏng vấn
                    </CardTitle>
                    {myEvaluation?.status === 'submitted' ? (
                      <Badge variant="success" className="gap-1">
                        <Lock className="h-3 w-3" aria-hidden="true" />
                        Đã gửi
                      </Badge>
                    ) : myEvaluation?.status === 'draft' ? (
                      <Badge variant="warning">Bản nháp</Badge>
                    ) : null}
                  </div>
                  <CardDescription>
                    {myEvaluation?.status === 'submitted'
                      ? 'Đánh giá đã được gửi và không thể chỉnh sửa hoặc xóa.'
                      : 'Đánh giá ứng viên theo tiêu chí chuyên môn và đề xuất tuyển dụng.'}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {isEvaluationsLoading ? (
                    <div className="space-y-3">
                      <Skeleton className="h-6 w-32" />
                      <Skeleton className="h-16 w-full" />
                    </div>
                  ) : evaluationsError ? (
                    <p role="alert" className="text-sm font-medium text-destructive">
                      {evaluationsError}
                    </p>
                  ) : (
                    <>
                      {actionError && !isConfirmSubmitOpen ? (
                        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive">
                          {actionError}
                        </p>
                      ) : null}

                      {myEvaluation?.status === 'submitted' ? (
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <RatingStars value={myEvaluation.rating} />
                            {myEvaluation.recommendation ? (
                              <Badge variant="info">
                                {EVALUATION_RECOMMENDATION_LABELS[myEvaluation.recommendation]}
                              </Badge>
                            ) : null}
                          </div>

                          <dl className="space-y-2 text-sm">
                            {myEvaluation.strengths ? (
                              <div>
                                <dt className="font-medium text-foreground">Điểm mạnh</dt>
                                <dd className="whitespace-pre-wrap text-muted-foreground">{myEvaluation.strengths}</dd>
                              </div>
                            ) : null}
                            {myEvaluation.weaknesses ? (
                              <div>
                                <dt className="font-medium text-foreground">Điểm cần cải thiện</dt>
                                <dd className="whitespace-pre-wrap text-muted-foreground">{myEvaluation.weaknesses}</dd>
                              </div>
                            ) : null}
                            {myEvaluation.notes ? (
                              <div>
                                <dt className="font-medium text-foreground">Ghi chú</dt>
                                <dd className="whitespace-pre-wrap text-muted-foreground">{myEvaluation.notes}</dd>
                              </div>
                            ) : null}
                          </dl>

                          <p className="text-xs text-muted-foreground">
                            Đã gửi lúc {formatDateTime(myEvaluation.submitted_at ?? myEvaluation.updated_at)}
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div className="grid gap-3 sm:grid-cols-2">
                            <Select
                              id="interviewer-rating"
                              name="rating"
                              label="Điểm đánh giá"
                              value={String(formValues.rating)}
                              onChange={(e) =>
                                setFormValues((prev) => ({
                                  ...prev,
                                  rating: Number(e.target.value),
                                }))
                              }
                              disabled={submittingEvaluation}
                            >
                              {[1, 2, 3, 4, 5].map((score) => (
                                <option key={score} value={score}>
                                  {score} / 5
                                </option>
                              ))}
                            </Select>
                            <Select
                              id="interviewer-recommendation"
                              name="recommendation"
                              label="Đề xuất"
                              value={formValues.recommendation}
                              onChange={(e) =>
                                setFormValues((prev) => ({
                                  ...prev,
                                  recommendation: e.target.value as EvaluationRecommendation | '',
                                }))
                              }
                              disabled={submittingEvaluation}
                            >
                              {RECOMMENDATION_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>
                                  {opt.label}
                                </option>
                              ))}
                            </Select>
                          </div>

                          <Textarea
                            id="interviewer-strengths"
                            name="strengths"
                            label="Điểm mạnh"
                            value={formValues.strengths}
                            maxLength={1000}
                            rows={2}
                            onChange={(e) =>
                              setFormValues((prev) => ({
                                ...prev,
                                strengths: e.target.value,
                              }))
                            }
                            disabled={submittingEvaluation}
                          />
                          <Textarea
                            id="interviewer-weaknesses"
                            name="weaknesses"
                            label="Điểm cần cải thiện"
                            value={formValues.weaknesses}
                            maxLength={1000}
                            rows={2}
                            onChange={(e) =>
                              setFormValues((prev) => ({
                                ...prev,
                                weaknesses: e.target.value,
                              }))
                            }
                            disabled={submittingEvaluation}
                          />
                          <Textarea
                            id="interviewer-notes"
                            name="notes"
                            label="Ghi chú"
                            value={formValues.notes}
                            maxLength={2000}
                            rows={2}
                            onChange={(e) =>
                              setFormValues((prev) => ({
                                ...prev,
                                notes: e.target.value,
                              }))
                            }
                            disabled={submittingEvaluation}
                          />

                          <div className="flex flex-wrap items-center gap-2 pt-1">
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={handleSaveDraft}
                              isLoading={submittingEvaluation}
                            >
                              Lưu nháp
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              onClick={handleOpenConfirmSubmit}
                              disabled={submittingEvaluation}
                            >
                              <Send className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                              Gửi đánh giá
                            </Button>
                            {myEvaluation ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="text-destructive hover:text-destructive"
                                onClick={handleDeleteDraft}
                                disabled={submittingEvaluation}
                              >
                                <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                                Xóa nháp
                              </Button>
                            ) : null}
                          </div>

                          <p className="text-xs text-muted-foreground italic">
                            Đánh giá từ các đồng nghiệp khác sẽ hiển thị sau khi bạn gửi đánh giá của mình.
                          </p>
                        </div>
                      )}

                      {myEvaluation?.status === 'submitted' && otherEvaluations.length > 0 ? (
                        <div className="border-t pt-4 space-y-3">
                          <h4 className="text-sm font-semibold text-foreground">
                            Đánh giá từ đồng nghiệp ({otherEvaluations.length})
                          </h4>
                          <div className="space-y-3">
                            {otherEvaluations.map((oe) => (
                              <div key={oe.id} className="rounded-lg border bg-muted/20 p-3 space-y-1.5">
                                <div className="flex items-center justify-between">
                                  <Badge variant="neutral">Đồng nghiệp</Badge>
                                  <RatingStars value={oe.rating} />
                                </div>
                                {oe.recommendation ? (
                                  <Badge variant="info">
                                    {EVALUATION_RECOMMENDATION_LABELS[oe.recommendation]}
                                  </Badge>
                                ) : null}
                                {oe.strengths ? (
                                  <p className="text-xs text-muted-foreground">
                                    <strong className="text-foreground">Điểm mạnh:</strong> {oe.strengths}
                                  </p>
                                ) : null}
                                {oe.weaknesses ? (
                                  <p className="text-xs text-muted-foreground">
                                    <strong className="text-foreground">Cần cải thiện:</strong> {oe.weaknesses}
                                  </p>
                                ) : null}
                                {oe.notes ? (
                                  <p className="text-xs text-muted-foreground">
                                    <strong className="text-foreground">Ghi chú:</strong> {oe.notes}
                                  </p>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </>
                  )}
                </CardContent>
              </Card>
            ) : null}
          </div>
        </div>
      )}

      {isConfirmSubmitOpen ? (
        <Modal
          size="sm"
          onClose={handleCloseConfirmSubmit}
          ariaLabel="Xác nhận gửi đánh giá"
          title="Xác nhận gửi đánh giá"
          description="Bạn đã hoàn tất đánh giá ứng viên? Vui lòng kiểm tra điểm số, nhận xét và đề xuất tuyển dụng trước khi gửi."
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                onClick={handleCloseConfirmSubmit}
                disabled={submittingEvaluation}
              >
                Quay lại
              </Button>
              <Button
                type="button"
                onClick={handleConfirmSubmit}
                isLoading={submittingEvaluation}
                disabled={submittingEvaluation}
              >
                <Send className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                Gửi đánh giá
              </Button>
            </>
          }
        >
          <div className="space-y-3 py-1">
            <div className="flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-foreground">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                aria-hidden="true"
              />
              <span>Sau khi gửi, phiếu đánh giá sẽ không thể chỉnh sửa hoặc xóa.</span>
            </div>

            <div className="space-y-2 rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
              <div className="flex items-center justify-between">
                <span>Điểm đánh giá:</span>
                <span className="font-semibold text-foreground">
                  {formValues.rating} / 5
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Đề xuất:</span>
                <span className="font-medium text-foreground">
                  {formValues.recommendation
                    ? EVALUATION_RECOMMENDATION_LABELS[formValues.recommendation]
                    : 'Chưa có đề xuất'}
                </span>
              </div>
            </div>

            {actionError ? (
              <p
                role="alert"
                className="rounded-md bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive"
              >
                {actionError}
              </p>
            ) : null}
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
