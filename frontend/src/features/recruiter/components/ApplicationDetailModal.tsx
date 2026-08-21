import { useCallback, useEffect, useState } from 'react'
import {
  Award,
  Briefcase,
  Building2,
  CalendarDays,
  FileText,
  GraduationCap,
  Languages,
  Mail,
  Phone,
  RefreshCw,
  Sparkles,
  User,
  Wrench,
} from 'lucide-react'
import { getApplicationDetail, getApplicationMatch } from '@/api/applications'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Spinner } from '@/components/ui/spinner'
import { Badge } from '@/components/ui/badge'
import { ApplicationStatusBadge } from '@/components/common/ApplicationStatusBadge'
import { MatchScoreCard } from '@/features/ai/components/MatchScoreCard'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { StatusUpdateModal } from './StatusUpdateModal'
import type { MatchResult } from '@/types/ai'
import type { Application, ApplicationDetail } from '@/types/application'

export interface ApplicationDetailModalProps {
  application: Application
  onClose: () => void
  onStatusChange?: (updated: Application) => void
}

function formatDate(dateString: string | null): string {
  if (!dateString) return ''
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function SectionTitle({
  icon,
  children,
}: {
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
        {icon}
      </span>
      {children}
    </h3>
  )
}

function DigitalCV({
  parsedData,
}: {
  parsedData: ApplicationDetail['resume']
}) {
  const data = parsedData?.parsed_data

  if (!parsedData) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed bg-muted/30 px-6 py-10 text-center">
        <FileText className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium text-foreground">Chưa có hồ sơ CV</p>
        <p className="text-sm text-muted-foreground">
          Ứng viên chưa tải lên CV, chưa có dữ liệu để hiển thị.
        </p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed bg-muted/30 px-6 py-10 text-center">
        <FileText className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium text-foreground">CV chưa có dữ liệu</p>
        <p className="text-sm text-muted-foreground">
          Hồ sơ CV chưa được trích xuất dữ liệu, không có gì để hiển thị.
        </p>
      </div>
    )
  }

  const hasContact = data.email || data.phone

  return (
    <div className="space-y-5">
      {data.full_name || data.title ? (
        <div>
          {data.full_name ? (
            <p className="text-lg font-semibold text-foreground">
              {data.full_name}
            </p>
          ) : null}
          {data.title ? (
            <p className="text-sm text-muted-foreground">{data.title}</p>
          ) : null}
        </div>
      ) : null}

      {hasContact ? (
        <div className="space-y-1.5 text-sm">
          {data.email ? (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Mail className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{data.email}</span>
            </p>
          ) : null}
          {data.phone ? (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Phone className="h-4 w-4 shrink-0" aria-hidden="true" />
              {data.phone}
            </p>
          ) : null}
        </div>
      ) : null}

      {data.summary ? (
        <div className="space-y-1.5">
          <SectionTitle icon={<User className="h-3.5 w-3.5" aria-hidden="true" />}>
            Giới thiệu
          </SectionTitle>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {data.summary}
          </p>
        </div>
      ) : null}

      {data.total_years_experience != null ? (
        <p className="text-sm text-muted-foreground">
          Tổng kinh nghiệm: {data.total_years_experience} năm
        </p>
      ) : null}

      {data.skills.length > 0 ? (
        <div className="space-y-2">
          <SectionTitle icon={<Wrench className="h-3.5 w-3.5" aria-hidden="true" />}>
            Kỹ năng
          </SectionTitle>
          <div className="flex flex-wrap gap-2">
            {data.skills.map((skill) => (
              <Badge key={skill} variant="outline-ai">
                {skill}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      {data.experiences.length > 0 ? (
        <div className="space-y-2">
          <SectionTitle icon={<Briefcase className="h-3.5 w-3.5" aria-hidden="true" />}>
            Kinh nghiệm làm việc
          </SectionTitle>
          <div className="space-y-3">
            {data.experiences.map((exp, index) => (
              <div
                key={index}
                className="rounded-lg border bg-muted/20 px-4 py-3"
              >
                {exp.position || exp.company ? (
                  <p className="text-sm font-medium text-foreground">
                    {[exp.position, exp.company].filter(Boolean).join(' · ')}
                  </p>
                ) : null}
                {exp.start_date || exp.end_date ? (
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {[exp.start_date, exp.end_date].filter(Boolean).join(' — ')}
                    {exp.is_current ? ' (Hiện tại)' : ''}
                  </p>
                ) : null}
                {exp.description ? (
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    {exp.description}
                  </p>
                ) : null}
                {exp.skills_used.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {exp.skills_used.map((skill) => (
                      <Badge key={skill} variant="neutral">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {data.education.length > 0 ? (
        <div className="space-y-2">
          <SectionTitle icon={<GraduationCap className="h-3.5 w-3.5" aria-hidden="true" />}>
            Học vấn
          </SectionTitle>
          <div className="space-y-3">
            {data.education.map((edu, index) => (
              <div
                key={index}
                className="rounded-lg border bg-muted/20 px-4 py-3"
              >
                {edu.institution ? (
                  <p className="text-sm font-medium text-foreground">
                    {edu.institution}
                  </p>
                ) : null}
                {edu.degree || edu.field_of_study ? (
                  <p className="mt-0.5 text-sm text-muted-foreground">
                    {[edu.degree, edu.field_of_study].filter(Boolean).join(' · ')}
                  </p>
                ) : null}
                {edu.start_year || edu.end_year ? (
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {[edu.start_year, edu.end_year].filter(Boolean).join(' — ')}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {data.certifications.length > 0 ? (
        <div className="space-y-2">
          <SectionTitle icon={<Award className="h-3.5 w-3.5" aria-hidden="true" />}>
            Chứng chỉ
          </SectionTitle>
          <div className="flex flex-wrap gap-2">
            {data.certifications.map((cert) => (
              <Badge key={cert} variant="info">
                {cert}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      {data.languages.length > 0 ? (
        <div className="space-y-2">
          <SectionTitle icon={<Languages className="h-3.5 w-3.5" aria-hidden="true" />}>
            Ngoại ngữ
          </SectionTitle>
          <div className="flex flex-wrap gap-2">
            {data.languages.map((lang) => (
              <Badge key={lang} variant="neutral">
                {lang}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function ApplicationDetailModal({
  application,
  onClose,
  onStatusChange,
}: ApplicationDetailModalProps) {
  const [state, setState] = useState<{
    kind: 'loading' | 'error' | 'success'
    detail?: ApplicationDetail
    message?: string
  }>({ kind: 'loading' })
  const [showStatusUpdate, setShowStatusUpdate] = useState(false)
  const [matchState, setMatchState] = useState<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'error'; message: string }
    | { kind: 'success'; result: MatchResult }
  >({ kind: 'idle' })

  const runMatch = useCallback(() => {
    setMatchState({ kind: 'loading' })
    getApplicationMatch(application.id)
      .then((result) => setMatchState({ kind: 'success', result }))
      .catch((err) => {
        setMatchState({
          kind: 'error',
          message: getFriendlyErrorMessage(err),
        })
      })
  }, [application.id])

  const load = useCallback(() => {
    let active = true
    setState({ kind: 'loading' })
    getApplicationDetail(application.id)
      .then((detail) => {
        if (active) setState({ kind: 'success', detail })
      })
      .catch((err) => {
        if (active) {
          setState({ kind: 'error', message: getFriendlyErrorMessage(err) })
        }
      })
    return () => {
      active = false
    }
  }, [application.id])

  useEffect(() => {
    return load()
  }, [load])

  const detail = state.detail
  const candidateName =
    detail?.candidate?.full_name ||
    application.candidate?.full_name ||
    `Ứng viên ${application.candidate_id.slice(0, 8)}`
  const candidateTitle = detail?.candidate?.title ?? 'Hồ sơ ứng viên'

  const handleStatusUpdated = (updated: Application) => {
    setShowStatusUpdate(false)
    if (state.kind === 'success' && state.detail) {
      setState({
        kind: 'success',
        detail: { ...state.detail, status: updated.status },
      })
    }
    onStatusChange?.(updated)
  }

  return (
    <Modal
      onClose={onClose}
      size="lg"
      ariaLabel="Chi tiết đơn ứng tuyển"
      title={
        <span className="flex items-center gap-2">
          <User className="h-5 w-5 text-primary" aria-hidden="true" />
          {candidateName}
        </span>
      }
      description={candidateTitle}
      footer={
        <>
          {state.kind === 'success' && detail ? (
            <Button
              variant="outline"
              onClick={() => setShowStatusUpdate(true)}
              disabled={!onStatusChange}
            >
              Cập nhật trạng thái
            </Button>
          ) : null}
          <Button variant="ghost" onClick={onClose}>
            Đóng
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        {state.kind === 'loading' ? (
          <div className="flex items-center justify-center gap-3 py-10 text-muted-foreground">
            <Spinner size="md" />
            <span>Đang tải chi tiết đơn ứng tuyển...</span>
          </div>
        ) : null}

        {state.kind === 'error' ? (
          <div className="space-y-4 py-4 text-center">
            <p role="alert" className="text-sm font-medium text-destructive">
              {state.message}
            </p>
            <Button variant="outline" onClick={load}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {state.kind === 'success' && detail ? (
          <>
            <div className="space-y-2 rounded-xl border bg-muted/20 px-4 py-3">
              <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Building2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                {detail.job_title}
                {detail.company_name ? ` · ${detail.company_name}` : ''}
              </p>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <ApplicationStatusBadge status={detail.status} />
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <CalendarDays className="h-3.5 w-3.5" aria-hidden="true" />
                  Nộp đơn: {formatDate(detail.created_at) || 'Không có ngày nộp đơn'}
                </span>
              </div>
            </div>

            <div className="space-y-3">
              <SectionTitle icon={<FileText className="h-3.5 w-3.5" aria-hidden="true" />}>
                Hồ sơ CV
              </SectionTitle>
              <DigitalCV parsedData={detail.resume} />
            </div>

            <div className="space-y-3">
              <SectionTitle icon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}>
                AI Match
              </SectionTitle>
              {!detail.resume?.parsed_data ? (
                <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed bg-muted/30 px-6 py-8 text-center">
                  <Sparkles className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
                  <p className="text-sm font-medium text-foreground">
                    Chưa có dữ liệu CV để phân tích
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Ứng viên chưa có CV được trích xuất, chưa thể tính điểm đối sánh.
                  </p>
                </div>
              ) : matchState.kind === 'idle' ? (
                <div className="rounded-xl border bg-muted/20 px-4 py-4">
                  <p className="text-sm text-muted-foreground">
                    Phân tích mức độ phù hợp của ứng viên với công việc bằng AI.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={runMatch}
                  >
                    <Sparkles className="h-4 w-4" aria-hidden="true" />
                    Phân tích AI
                  </Button>
                </div>
              ) : matchState.kind === 'loading' ? (
                <div className="flex items-center gap-3 rounded-xl border bg-muted/30 px-4 py-6 text-sm text-muted-foreground">
                  <Spinner size="md" />
                  <span>Đang phân tích mức độ phù hợp...</span>
                </div>
              ) : matchState.kind === 'error' ? (
                <div className="space-y-3 rounded-xl border border-destructive/30 bg-muted/20 px-4 py-4">
                  <p role="alert" className="text-sm font-medium text-destructive">
                    {matchState.message}
                  </p>
                  <Button variant="outline" size="sm" onClick={runMatch}>
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    Thử lại
                  </Button>
                </div>
              ) : matchState.kind === 'success' && matchState.result ? (
                <MatchScoreCard
                  matchResult={matchState.result}
                  candidate={detail.resume.parsed_data}
                  job={detail.parsed_job}
                />
              ) : null}
            </div>
          </>
        ) : null}
      </div>

      {showStatusUpdate && detail ? (
        <StatusUpdateModal
          application={detail}
          onClose={() => setShowStatusUpdate(false)}
          onSuccess={handleStatusUpdated}
        />
      ) : null}
    </Modal>
  )
}