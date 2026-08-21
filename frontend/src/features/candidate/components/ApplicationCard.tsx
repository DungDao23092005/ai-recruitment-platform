import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, ExternalLink, MapPin, Undo2, CheckCircle2, XCircle } from 'lucide-react'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button, buttonVariants } from '@/components/ui/button'
import { ApplicationStatusBadge } from '@/components/common/ApplicationStatusBadge'
import { withdrawApplication } from '@/api/applications'
import { candidateActionInterview } from '@/api/interviews'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'
import type { ApplicationStatus, ApplicationWithJob } from '@/types/application'

export const WITHDRAWABLE_STATUSES: ApplicationStatus[] = [
  'applied',
  'under_review',
  'shortlisted',
  'interviewing',
]

export interface ApplicationCardProps {
  application: ApplicationWithJob
  detailPath?: string
  onWithdrawn?: (applicationId: string) => void
}

function formatAppliedDate(dateString: string): string {
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleDateString('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function companyMonogram(companyName: string): string {
  const trimmed = companyName.trim()
  if (!trimmed) {
    return 'C'
  }
  const words = trimmed.split(/\s+/)
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase()
  }
  return (
    words
      .slice(0, 2)
      .map((word) => word[0])
      .join('')
      .toUpperCase()
  )
}

export function ApplicationCard({
  application,
  detailPath = '/candidate/jobs',
  onWithdrawn,
}: ApplicationCardProps) {
  const { id, job_title, company_name, status, created_at } = application
  const [withdrawing, setWithdrawing] = useState(false)
  const [withdrawError, setWithdrawError] = useState<string | null>(null)
  
  // Interview action states - track by interview ID
  const [interviewLoading, setInterviewLoading] = useState<string | null>(null)
  const [interviewError, setInterviewError] = useState<Record<string, string | null>>({})

  const canWithdraw = WITHDRAWABLE_STATUSES.includes(status)
  const appliedDate = formatAppliedDate(created_at)
  const rawCompanyName = company_name ?? 'Công ty'
  const companyLabel = company_name ? `Công ty ${company_name}` : rawCompanyName

  const handleWithdraw = async () => {
    setWithdrawing(true)
    setWithdrawError(null)
    try {
      await withdrawApplication(id)
      onWithdrawn?.(id)
    } catch (err) {
      setWithdrawError(getFriendlyErrorMessage(err))
    } finally {
      setWithdrawing(false)
    }
  }

  const handleInterviewAction = async (interviewId: string, action: 'confirm' | 'decline', candidateNotes?: string) => {
    setInterviewLoading(interviewId)
    setInterviewError(prev => ({ ...prev, [interviewId]: null }))
    try {
      await candidateActionInterview(
        application.id,
        interviewId,
        action,
        candidateNotes
      )
    } catch (err) {
      setInterviewError(prev => ({ ...prev, [interviewId]: getFriendlyErrorMessage(err) }))
    } finally {
      setInterviewLoading(null)
    }
  }

  const handleConfirm = (interviewId: string) => {
    handleInterviewAction(interviewId, 'confirm')
  }

  const handleDecline = (interviewId: string) => {
    const reason = prompt('Vui lòng nhập lý do từ chối:')
    if (reason === null) {
      return
    }
    if (!reason.trim()) {
      return
    }
    handleInterviewAction(interviewId, 'decline', reason.trim())
  }

  return (
    <Card className="border-border/70 bg-card shadow-soft">
      <CardHeader className="gap-3">
        <div className="flex items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 font-display text-sm font-bold text-primary ring-1 ring-primary/15"
            aria-hidden="true"
          >
            {companyMonogram(rawCompanyName)}
          </div>
          <div className="min-w-0 flex-1">
            <CardTitle className="line-clamp-1 font-display text-lg font-semibold leading-snug text-foreground">
              {job_title}
            </CardTitle>
            <p className="mt-0.5 truncate text-sm text-muted-foreground">
              {companyLabel}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <ApplicationStatusBadge status={status} />
        </div>
        {appliedDate ? (
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <CalendarDays className="h-4 w-4 text-primary/70" aria-hidden="true" />
            Ứng tuyển: {appliedDate}
          </p>
        ) : null}
        {application.interviews && application.interviews.length > 0 ? (
          <>
            {/* Scheduled interviews with action buttons */}
            {application.interviews.filter(i => i.status === 'scheduled').length > 0 && (
              <div className="mt-2 rounded-md border border-primary/20 bg-primary/5 p-3">
                <p className="mb-1 font-semibold text-primary">Lịch phỏng vấn sắp tới</p>
                {application.interviews.filter(i => i.status === 'scheduled').map(interview => (
                  <div key={interview.id} className="text-sm text-muted-foreground">
                    <p><strong>Thời gian:</strong> {new Date(interview.scheduled_at).toLocaleString('vi-VN')}</p>
                    <p><strong>Hình thức:</strong> {
                      interview.interview_type === 'technical' ? 'Chuyên môn' :
                      interview.interview_type === 'behavioral' ? 'Hành vi' :
                      interview.interview_type === 'hr' ? 'Nhân sự' :
                      'Case Study'
                    }</p>
                    {(interview.meeting_url || interview.location) && (
                      <p className="mt-1">
                        {interview.meeting_url ? (
                          <a href={interview.meeting_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">Tham gia Meeting</a>
                        ) : (
                          <span><strong>Địa điểm:</strong> {interview.location}</span>
                        )}
                      </p>
                    )}
                    <div className="mt-2 flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1"
                        onClick={() => handleConfirm(interview.id)}
                        disabled={interviewLoading === interview.id}
                        isLoading={interviewLoading === interview.id}
                      >
                        <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                        Xác nhận tham gia
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        className="flex-1"
                        onClick={() => handleDecline(interview.id)}
                        disabled={interviewLoading === interview.id}
                        isLoading={interviewLoading === interview.id}
                      >
                        <XCircle className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                        Từ chối
                      </Button>
                    </div>
                    {interviewError[interview.id] && (
                      <p className="mt-2 text-sm text-destructive" role="alert">
                        {interviewError[interview.id]}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
            {/* Confirmed interviews */}
            {application.interviews.filter(i => i.status === 'candidate_confirmed').length > 0 && (
              <div className="mt-2 space-y-2">
                {application.interviews.filter(i => i.status === 'candidate_confirmed').map(interview => (
                  <div key={interview.id} className="rounded-lg border border-success/20 bg-success/5 p-3 text-sm">
                    <div className="flex justify-between items-start mb-2">
                      <p className="font-semibold text-success">Phỏng vấn {
                        interview.interview_type === 'technical' ? 'Chuyên môn' :
                        interview.interview_type === 'behavioral' ? 'Hành vi' :
                        interview.interview_type === 'hr' ? 'Nhân sự' :
                        'Case Study'
                      }</p>
                      <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 border-transparent bg-success/10 text-success">
                        Đã xác nhận
                      </span>
                    </div>
                    <div className="space-y-1 text-muted-foreground">
                      <p className="flex items-center gap-2"><CalendarDays className="h-3.5 w-3.5" /> {new Date(interview.scheduled_at).toLocaleString('vi-VN')} ({interview.duration_minutes} phút)</p>
                      {interview.meeting_url && <p className="flex items-center gap-2"><ExternalLink className="h-3.5 w-3.5" /> <a href={interview.meeting_url} target="_blank" rel="noopener noreferrer" className="hover:underline">{interview.meeting_url}</a></p>}
                      {interview.location && <p className="flex items-center gap-2"><MapPin className="h-3.5 w-3.5" /> {interview.location}</p>}
                      {interview.candidate_notes && <p className="mt-2 text-xs italic bg-success/5 border border-success/20 p-2 rounded text-success">Phản hồi: {interview.candidate_notes}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {/* Declined interviews */}
            {application.interviews.filter(i => i.status === 'candidate_declined').length > 0 && (
              <div className="mt-2 space-y-2">
                {application.interviews.filter(i => i.status === 'candidate_declined').map(interview => (
                  <div key={interview.id} className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm">
                    <div className="flex justify-between items-start mb-2">
                      <p className="font-semibold text-destructive">Phỏng vấn {
                        interview.interview_type === 'technical' ? 'Chuyên môn' :
                        interview.interview_type === 'behavioral' ? 'Hành vi' :
                        interview.interview_type === 'hr' ? 'Nhân sự' :
                        'Case Study'
                      }</p>
                      <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 border-transparent bg-destructive/10 text-destructive">
                        Đã từ chối
                      </span>
                    </div>
                    <div className="space-y-1 text-muted-foreground">
                      <p className="flex items-center gap-2"><CalendarDays className="h-3.5 w-3.5" /> {new Date(interview.scheduled_at).toLocaleString('vi-VN')} ({interview.duration_minutes} phút)</p>
                      {interview.meeting_url && <p className="flex items-center gap-2"><ExternalLink className="h-3.5 w-3.5" /> <a href={interview.meeting_url} target="_blank" rel="noopener noreferrer" className="hover:underline">{interview.meeting_url}</a></p>}
                      {interview.location && <p className="flex items-center gap-2"><MapPin className="h-3.5 w-3.5" /> {interview.location}</p>}
                      {interview.candidate_notes && <p className="mt-2 text-xs italic bg-destructive/5 border border-destructive/20 p-2 rounded text-destructive">Lý do: {interview.candidate_notes}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : null}
        {withdrawError ? (
          <p
            role="alert"
            className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
          >
            {withdrawError}
          </p>
        ) : null}
      </CardContent>
      <CardFooter className="flex flex-wrap items-center gap-2">
        <Link
          to={`${detailPath}/${application.job_id}`}
          className={cn(
            buttonVariants({ variant: 'outline', size: 'sm' }),
            'flex-1',
          )}
        >
          Xem việc làm
          <ExternalLink className="ml-1.5 h-3.5 w-3.5" aria-hidden="true" />
        </Link>
        {canWithdraw ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={handleWithdraw}
            isLoading={withdrawing}
            disabled={withdrawing}
          >
            <Undo2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            Rút đơn
          </Button>
        ) : null}
      </CardFooter>
    </Card>
  )
}