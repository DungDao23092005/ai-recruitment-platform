import { useEffect, useState } from 'react'
import {
  Lock,
  Mail,
  Phone,
  Briefcase,
  GraduationCap,
  Calendar,
  Send,
  Eye,
  Clock,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'
import { Modal } from '@/components/ui/modal'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { ErrorBanner } from '@/components/ui/error-banner'
import {
  createContactRequest,
  getCandidateContactDetails,
  getCandidatePreview,
} from '@/api/contactRequests'
import { CONTACT_REQUEST_UPDATED_DOM_EVENT } from '@/hooks/useNotificationStream'
import type {
  CandidateContactResponse,
  CandidatePreviewResponse,
} from '@/types/ai'
import { getFriendlyErrorMessage } from '@/utils/errors'

export interface CandidatePreviewModalProps {
  candidateId: string
  onClose: () => void
  onRequestSent?: () => void
}

export function CandidatePreviewModal({
  candidateId,
  onClose,
  onRequestSent,
}: CandidatePreviewModalProps) {
  const [preview, setPreview] = useState<CandidatePreviewResponse | null>(null)
  const [contactDetails, setContactDetails] =
    useState<CandidateContactResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)

  const loadPreview = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getCandidatePreview(candidateId)
      setPreview(data)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void loadPreview()
  }, [candidateId])

  useEffect(() => {
    const handleContactRequestUpdated = (event: Event) => {
      const customEvent = event as CustomEvent
      const detail = customEvent.detail
      if (!detail) return

      // Ignore if event is definitely for another candidate or request
      if (detail.candidate_id && detail.candidate_id !== candidateId) return
      if (
        preview?.contact_request_id &&
        detail.entity_id &&
        detail.entity_id !== preview.contact_request_id
      ) {
        return
      }

      void loadPreview()
    }

    window.addEventListener(
      CONTACT_REQUEST_UPDATED_DOM_EVENT,
      handleContactRequestUpdated,
    )
    return () => {
      window.removeEventListener(
        CONTACT_REQUEST_UPDATED_DOM_EVENT,
        handleContactRequestUpdated,
      )
    }
  }, [candidateId, preview?.contact_request_id])

  const handleSendRequest = async () => {
    setActionLoading(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await createContactRequest(candidateId)
      setActionSuccess('Đã gửi yêu cầu kết nối tới ứng viên thành công.')
      setPreview((prev) =>
        prev
          ? {
              ...prev,
              contact_request_status: 'pending',
              can_request_contact: false,
            }
          : null,
      )
      onRequestSent?.()
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setActionLoading(false)
    }
  }

  const handleRevealContact = async () => {
    setActionLoading(true)
    setActionError(null)
    try {
      const details = await getCandidateContactDetails(candidateId)
      setContactDetails(details)
    } catch (err) {
      setActionError(getFriendlyErrorMessage(err))
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      size="lg"
      title="Hồ sơ ứng viên"
      ariaLabel="Chi tiết hồ sơ ứng viên"
    >
      <div className="space-y-6 p-5 sm:p-6 max-h-[75vh] overflow-y-auto">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-12 space-y-3">
            <Spinner className="h-8 w-8 text-primary" />
            <p className="text-sm text-muted-foreground">
              Đang tải thông tin chuyên môn ứng viên...
            </p>
          </div>
        ) : error ? (
          <ErrorBanner message={error} onRetry={() => void loadPreview()} />
        ) : preview ? (
          <>
            {/* Privacy Protection Notice Banner */}
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex items-start gap-3">
              <Lock className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              <div className="space-y-1 text-xs">
                <p className="font-semibold text-foreground">
                  Bảo vệ quyền riêng tư ứng viên (Zero PII Exposure)
                </p>
                <p className="text-muted-foreground leading-relaxed">
                  Email và số điện thoại của ứng viên được mã hóa bảo mật. Bạn có thể gửi yêu cầu kết nối để được ứng viên cấp quyền xem thông tin liên hệ trực tiếp.
                </p>
              </div>
            </div>

            {/* Candidate Header & Summary */}
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-base font-bold text-foreground">
                    {preview.full_name || 'Chưa cập nhật họ tên'}
                  </h3>
                  <p className="text-sm font-medium text-muted-foreground">
                    {preview.title || 'Chưa cập nhật chức danh'}
                  </p>
                </div>
                {preview.total_years_experience != null ? (
                  <Badge variant="outline-ai" className="text-xs">
                    {preview.total_years_experience} năm kinh nghiệm
                  </Badge>
                ) : null}
              </div>

              {preview.summary ? (
                <div className="rounded-lg bg-muted/40 p-3 text-sm text-foreground leading-relaxed">
                  {preview.summary}
                </div>
              ) : null}
            </div>

            {/* Skills */}
            {preview.skills.length > 0 ? (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Kỹ năng chuyên môn
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {preview.skills.map((skill) => (
                    <Badge key={skill} variant="neutral">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Work Experiences */}
            {preview.experiences && preview.experiences.length > 0 ? (
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Briefcase className="h-3.5 w-3.5" />
                  Kinh nghiệm làm việc
                </h4>
                <div className="space-y-3">
                  {preview.experiences.map((exp, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-1.5"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold text-sm text-foreground">
                          {exp.position || 'Vị trí làm việc'}
                        </span>
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {exp.start_date || '—'} -{' '}
                          {exp.is_current ? 'Hiện tại' : exp.end_date || '—'}
                        </span>
                      </div>
                      <p className="text-xs font-medium text-primary">
                        {exp.company || 'Doanh nghiệp'}
                      </p>
                      {exp.description ? (
                        <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
                          {exp.description}
                        </p>
                      ) : null}
                      {exp.skills_used && exp.skills_used.length > 0 ? (
                        <div className="flex flex-wrap gap-1 pt-1">
                          {exp.skills_used.map((s) => (
                            <span
                              key={s}
                              className="inline-block rounded-md bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
                            >
                              {s}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Education */}
            {preview.education && preview.education.length > 0 ? (
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <GraduationCap className="h-3.5 w-3.5" />
                  Học vấn & Bằng cấp
                </h4>
                <div className="space-y-2">
                  {preview.education.map((edu, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-1"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold text-sm text-foreground">
                          {edu.institution || 'Cơ sở đào tạo'}
                        </span>
                        {edu.start_year || edu.end_year ? (
                          <span className="text-xs text-muted-foreground">
                            {edu.start_year || '—'} - {edu.end_year || '—'}
                          </span>
                        ) : null}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {[edu.degree, edu.field_of_study]
                          .filter(Boolean)
                          .join(' • ')}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Contact Authorization Section */}
            <div className="border-t border-border/70 pt-5 space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Thông tin liên hệ & Quyền truy cập
                </h4>
                {preview.contact_request_status === 'accepted' ? (
                  <Badge variant="success" className="gap-1">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    Đã được cấp quyền
                  </Badge>
                ) : preview.contact_request_status === 'pending' ? (
                  <Badge variant="warning" className="gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    Đang chờ phản hồi
                  </Badge>
                ) : preview.contact_request_status === 'declined' ? (
                  <Badge variant="destructive" className="gap-1">
                    <AlertCircle className="h-3.5 w-3.5" />
                    Đã từ chối
                  </Badge>
                ) : preview.contact_request_status === 'revoked' ? (
                  <Badge variant="neutral" className="gap-1">
                    <AlertCircle className="h-3.5 w-3.5" />
                    Đã thu hồi quyền
                  </Badge>
                ) : null}
              </div>

              {/* Revealed Contact Details Card */}
              {contactDetails ? (
                <div className="rounded-xl border border-success/30 bg-success/5 p-4 space-y-3 animate-fade-in">
                  <div className="flex items-center gap-2 text-success font-semibold text-sm">
                    <CheckCircle2 className="h-4 w-4" />
                    <span>Thông tin liên hệ chính thức</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="font-medium text-foreground select-all">
                        {contactDetails.email}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Phone className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="font-medium text-foreground select-all">
                        {contactDetails.phone || 'Chưa cung cấp số điện thoại'}
                      </span>
                    </div>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Truy cập được ghi nhật ký kiểm toán vào lúc{' '}
                    {new Date(contactDetails.disclosed_at).toLocaleString('vi-VN')}.
                  </p>
                </div>
              ) : null}

              {actionError ? (
                <p role="alert" className="text-sm font-medium text-destructive">
                  {actionError}
                </p>
              ) : null}

              {actionSuccess ? (
                <p role="status" className="text-sm font-medium text-success">
                  {actionSuccess}
                </p>
              ) : null}

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
                <Button variant="outline" onClick={onClose}>
                  Đóng
                </Button>

                {preview.contact_request_status === 'accepted' ? (
                  !contactDetails ? (
                    <Button
                      onClick={handleRevealContact}
                      isLoading={actionLoading}
                      disabled={actionLoading}
                      className="gap-1.5"
                    >
                      <Eye className="h-4 w-4" />
                      Xem thông tin liên hệ
                    </Button>
                  ) : null
                ) : preview.contact_request_status === 'pending' ? (
                  <Button disabled variant="outline" className="gap-1.5">
                    <Clock className="h-4 w-4" />
                    Đang chờ ứng viên phản hồi
                  </Button>
                ) : preview.can_request_contact ? (
                  <Button
                    onClick={handleSendRequest}
                    isLoading={actionLoading}
                    disabled={actionLoading}
                    className="gap-1.5"
                  >
                    <Send className="h-4 w-4" />
                    Gửi yêu cầu kết nối
                  </Button>
                ) : (
                  <div className="text-right">
                    <Button disabled variant="outline" className="gap-1.5">
                      <Clock className="h-4 w-4" />
                      Chưa thể gửi yêu cầu
                    </Button>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      {preview.contact_request_status === 'declined'
                        ? 'Thời gian chờ 30 ngày sau khi bị từ chối.'
                        : 'Thời gian chờ 90 ngày sau khi bị thu hồi quyền.'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </Modal>
  )
}
