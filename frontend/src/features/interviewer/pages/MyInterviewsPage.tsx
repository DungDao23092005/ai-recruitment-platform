import { useCallback, useEffect, useState } from 'react'
import {
  CalendarClock,
  FileText,
  MapPin,
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
import { Skeleton } from '@/components/ui/skeleton'
import {
  getInterviewerApplication,
  listMyAssignedInterviews,
} from '@/api/interviews'
import type {
  AssignedInterview,
  InterviewerApplication,
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

export function MyInterviewsPage() {
  const [interviews, setInterviews] = useState<AssignedInterview[]>([])
  const [selectedInterview, setSelectedInterview] =
    useState<AssignedInterview | null>(null)
  const [application, setApplication] =
    useState<InterviewerApplication | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isApplicationLoading, setIsApplicationLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
        </div>
      )}
    </div>
  )
}
