import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileCheck2, RefreshCw, ShieldCheck } from 'lucide-react'
import { getCandidateProfile } from '@/api/auth'
import {
  confirmMyResume,
  getMyResume,
  getMyResumeDraft,
  updateMyResumeDraft,
} from '@/api/ai'
import { ResumeUpload } from '@/features/candidate/components/ResumeUpload'
import { ParsedResumeView } from '@/features/candidate/components/ParsedResumeView'
import { ResumeReviewEditor } from '@/features/candidate/components/ResumeReviewEditor'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Skeleton } from '@/components/ui/skeleton'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/utils/cn'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { ParsedResume, ResumeRead } from '@/types/ai'

type ProfileStatus = 'loading' | 'missing' | 'ready' | 'error'
type ResumeStatus = 'loading' | 'loaded' | 'none' | 'error'

function isNotFoundError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    (error as { response?: { status?: number } }).response?.status === 404
  )
}

export function ResumeUploadPage() {
  const [profileStatus, setProfileStatus] = useState<ProfileStatus>('loading')
  const [resumeStatus, setResumeStatus] = useState<ResumeStatus>('loading')
  const [activeResume, setActiveResume] = useState<ResumeRead | null>(null)
  const [draft, setDraft] = useState<ResumeRead | null>(null)
  const [isReuploading, setIsReuploading] = useState(false)
  const [isSavingDraft, setIsSavingDraft] = useState(false)
  const [isConfirming, setIsConfirming] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [indexingWarning, setIndexingWarning] = useState<string | null>(null)

  const loadResume = useCallback(async () => {
    setResumeStatus('loading')
    try {
      let confirmed: ResumeRead | null = null
      let pending: ResumeRead | null = null

      try {
        confirmed = await getMyResume()
      } catch (error) {
        if (!isNotFoundError(error)) {
          throw error
        }
      }

      try {
        pending = await getMyResumeDraft()
      } catch (error) {
        if (!isNotFoundError(error)) {
          throw error
        }
      }

      setActiveResume(confirmed)
      setDraft(pending)
      setResumeStatus(confirmed || pending ? 'loaded' : 'none')
      setIsReuploading(false)
      setIndexingWarning(null)
    } catch {
      setResumeStatus('error')
    }
  }, [])

  const loadProfile = useCallback(async () => {
    setProfileStatus('loading')
    try {
      await getCandidateProfile()
      setProfileStatus('ready')
      void loadResume()
    } catch (error) {
      if (isNotFoundError(error)) {
        setProfileStatus('missing')
      } else {
        setProfileStatus('error')
      }
    }
  }, [loadResume])

  useEffect(() => {
    void loadProfile()
  }, [loadProfile])

  const handleParsed = useCallback((resume: ResumeRead) => {
    setDraft(resume)
    setResumeStatus('loaded')
    setIsReuploading(false)
    setActionError(null)
    setIndexingWarning(null)
  }, [])

  const handleSaveDraft = useCallback(
    async (parsed: ParsedResume) => {
      if (!draft) {
        return
      }
      setIsSavingDraft(true)
      setActionError(null)
      try {
        const updated = await updateMyResumeDraft(draft.id, parsed)
        setDraft(updated)
      } catch (error) {
        setActionError(getFriendlyErrorMessage(error))
      } finally {
        setIsSavingDraft(false)
      }
    },
    [draft],
  )

  const handleConfirm = useCallback(
    async (parsed: ParsedResume) => {
      if (!draft) {
        return
      }
      setIsConfirming(true)
      setActionError(null)
      try {
        const updated = await updateMyResumeDraft(draft.id, parsed)
        setDraft(updated)
        const result = await confirmMyResume(updated.id)
        setActiveResume(result.resume)
        setDraft(null)
        setIsReuploading(false)
        setIndexingWarning(
          result.indexing_status === 'failed' ? result.message : null,
        )
      } catch (error) {
        setActionError(getFriendlyErrorMessage(error))
      } finally {
        setIsConfirming(false)
      }
    },
    [draft],
  )

  const handleRetryIndexing = useCallback(async () => {
    if (!activeResume) {
      return
    }
    setIsConfirming(true)
    setActionError(null)
    try {
      const result = await confirmMyResume(activeResume.id)
      setActiveResume(result.resume)
      setIndexingWarning(
        result.indexing_status === 'failed' ? result.message : null,
      )
    } catch (error) {
      setActionError(getFriendlyErrorMessage(error))
    } finally {
      setIsConfirming(false)
    }
  }, [activeResume])

  const showUpload = resumeStatus === 'none' || isReuploading
  const showEditor = draft !== null && !isReuploading

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hồ sơ"
        title="Tải lên và xác nhận CV"
        description="Tải CV PDF, xem lại dữ liệu AI trích xuất và xác nhận trước khi dùng CV cho ghép nối hoặc tìm kiếm."
      />

      <div className="max-w-2xl space-y-6">
        {profileStatus === 'loading' ? (
          <div className="space-y-4">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : null}

        {profileStatus === 'error' ? (
          <ErrorBanner
            message="Không thể tải thông tin hồ sơ ứng viên."
            onRetry={() => void loadProfile()}
          />
        ) : null}

        {profileStatus === 'missing' ? (
          <div className="rounded-2xl border bg-muted/20 p-8 text-center">
            <p className="font-display text-lg font-semibold text-foreground">
              Hồ sơ ứng viên chưa được tạo
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Vui lòng tạo hồ sơ ứng viên trước khi tải CV.
            </p>
            <Link
              to="/candidate/profile"
              className={cn(buttonVariants({ variant: 'default' }), 'mt-5')}
            >
              Tạo hồ sơ ứng viên
            </Link>
          </div>
        ) : null}

        {profileStatus === 'ready' ? (
          <>
            {resumeStatus === 'loading' ? (
              <div className="space-y-4">
                <Skeleton className="h-40 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : null}

            {resumeStatus === 'error' ? (
              <ErrorBanner
                message="Không thể tải thông tin CV đã tải lên."
                onRetry={() => void loadResume()}
              />
            ) : null}

            {actionError ? <ErrorBanner message={actionError} /> : null}

            {indexingWarning ? (
              <div
                role="status"
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning"
              >
                <span>{indexingWarning}</span>
                {activeResume && !draft ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void handleRetryIndexing()}
                    isLoading={isConfirming}
                    loadingText="Đang thử lại..."
                  >
                    <RefreshCw aria-hidden="true" />
                    Thử lập chỉ mục lại
                  </Button>
                ) : null}
              </div>
            ) : null}

            {activeResume ? (
              <div className="space-y-4 rounded-2xl border bg-muted/20 p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="flex items-center gap-2 font-display text-lg font-semibold text-foreground">
                      <ShieldCheck
                        className="h-5 w-5 text-primary"
                        aria-hidden="true"
                      />
                      CV đang được sử dụng
                    </p>
                    {activeResume.title ? (
                      <p className="mt-1 text-sm text-muted-foreground">
                        {activeResume.title}
                      </p>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setIsReuploading(true)
                      setActionError(null)
                    }}
                  >
                    <RefreshCw aria-hidden="true" />
                    Cập nhật CV
                  </Button>
                </div>
                {activeResume.parsed_data ? (
                  <ParsedResumeView resume={activeResume.parsed_data} />
                ) : null}
              </div>
            ) : null}

            {resumeStatus === 'none' ? (
              <div className="rounded-2xl border bg-muted/20 p-6">
                <p className="flex items-center gap-2 font-display text-lg font-semibold text-foreground">
                  <FileCheck2
                    className="h-5 w-5 text-primary"
                    aria-hidden="true"
                  />
                  Chưa có CV nào được xác nhận
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Tải CV PDF để AI trích xuất thông tin. Bạn sẽ xem lại và xác
                  nhận trước khi CV được sử dụng.
                </p>
              </div>
            ) : null}

            {showUpload ? <ResumeUpload onParsed={handleParsed} /> : null}

            {draft && isReuploading ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => setIsReuploading(false)}
              >
                Quay lại CV đang chờ xác nhận
              </Button>
            ) : null}

            {showEditor && draft ? (
              <ResumeReviewEditor
                resume={draft}
                isSaving={isSavingDraft}
                isConfirming={isConfirming}
                replacingActive={activeResume !== null}
                onSave={(parsed) => void handleSaveDraft(parsed)}
                onConfirm={(parsed) => void handleConfirm(parsed)}
              />
            ) : null}

            {activeResume && !draft && !isReuploading ? (
              <p className="text-center text-xs text-muted-foreground">
                CV đã xác nhận mới nhất được dùng cho ghép nối, gợi ý và tìm
                kiếm ứng viên.
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}
