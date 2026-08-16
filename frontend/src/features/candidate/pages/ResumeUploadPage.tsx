import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileCheck2, RefreshCw } from 'lucide-react'
import { getCandidateProfile } from '@/api/auth'
import { getMyResume } from '@/api/ai'
import { ResumeUpload } from '@/features/candidate/components/ResumeUpload'
import { ParsedResumeView } from '@/features/candidate/components/ParsedResumeView'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Skeleton } from '@/components/ui/skeleton'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/utils/cn'
import type { ParsedResume } from '@/types/ai'

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
  const [resumeTitle, setResumeTitle] = useState<string | null>(null)
  const [parsedResume, setParsedResume] = useState<ParsedResume | null>(null)
  const [isReuploading, setIsReuploading] = useState(false)

  const loadResume = useCallback(async () => {
    setResumeStatus('loading')
    try {
      const resume = await getMyResume()
      setResumeTitle(resume.title)
      setParsedResume(resume.parsed_data)
      setResumeStatus('loaded')
      setIsReuploading(false)
    } catch (error) {
      if (isNotFoundError(error)) {
        setResumeTitle(null)
        setParsedResume(null)
        setResumeStatus('none')
      } else {
        setResumeStatus('error')
      }
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

  const handleParsed = useCallback(
    (resume: ParsedResume, fileName?: string) => {
      setParsedResume(resume)
      if (fileName) {
        setResumeTitle(fileName)
      }
      setResumeStatus('loaded')
      setIsReuploading(false)
    },
    [],
  )

  const showUpload = resumeStatus === 'none' || isReuploading

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hồ sơ"
        title="Tải lên CV"
        description="Tải lên CV PDF và để AI trích xuất hồ sơ chuyên môn của bạn."
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

            {resumeStatus === 'loaded' && !isReuploading ? (
              <div className="rounded-2xl border bg-muted/20 p-6">
                <p className="flex items-center gap-2 font-display text-lg font-semibold text-foreground">
                  <FileCheck2 className="h-5 w-5 text-primary" aria-hidden="true" />
                  CV đã được tải lên
                </p>
                {resumeTitle ? (
                  <p className="mt-1 text-sm text-muted-foreground">
                    {resumeTitle}
                  </p>
                ) : null}
                <Button
                  type="button"
                  variant="outline"
                  className="mt-4"
                  onClick={() => setIsReuploading(true)}
                >
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Cập nhật CV
                </Button>
              </div>
            ) : null}

            {showUpload ? <ResumeUpload onParsed={handleParsed} /> : null}

            {parsedResume ? <ParsedResumeView resume={parsedResume} /> : null}
          </>
        ) : null}
      </div>
    </div>
  )
}