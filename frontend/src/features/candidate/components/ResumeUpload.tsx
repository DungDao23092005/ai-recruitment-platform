import { useCallback, useRef, useState, type DragEvent } from 'react'
import { UploadCloud, FileText, RefreshCw } from 'lucide-react'
import { parseResume } from '@/api/ai'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/utils/cn'
import type { ParsedResume } from '@/types/ai'

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

function isCandidateProfileRequiredError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    (error as { response?: { status?: number; data?: { detail?: string } } })
      .response?.status === 400 &&
    (error as { response?: { data?: { detail?: string } } }).response?.data
      ?.detail === 'Candidate profile required'
  )
}

function getResumeUploadErrorMessage(error: unknown): string {
  if (isCandidateProfileRequiredError(error)) {
    return 'Hồ sơ ứng viên chưa được tạo. Vui lòng tạo hồ sơ trước khi tải CV.'
  }
  return getFriendlyErrorMessage(error)
}

export interface ResumeUploadProps {
  onParsed?: (resume: ParsedResume, fileName?: string) => void
}

export function ResumeUpload({ onParsed }: ResumeUploadProps) {
  const [dragActive, setDragActive] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [fileName, setFileName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const validateFile = useCallback((file: File): string | null => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      return 'Chỉ chấp nhận tệp PDF.'
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return 'Tệp quá lớn. Kích thước tối đa là 10MB.'
    }
    return null
  }, [])

  const handleFile = useCallback(
    async (file: File) => {
      const validationError = validateFile(file)
      if (validationError) {
        setError(validationError)
        return
      }

      setError(null)
      setFileName(file.name)
      setIsUploading(true)
      try {
        const parsed = await parseResume(file)
        onParsed?.(parsed, file.name)
      } catch (err) {
        setError(getResumeUploadErrorMessage(err))
      } finally {
        setIsUploading(false)
      }
    },
    [validateFile, onParsed],
  )

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      setDragActive(false)
      const file = event.dataTransfer.files[0]
      if (file) {
        void handleFile(file)
      }
    },
    [handleFile],
  )

  const handleFileInput = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (file) {
        void handleFile(file)
      }
    },
    [handleFile],
  )

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        aria-label="Tải lên CV PDF"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            inputRef.current?.click()
          }
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={cn(
          'flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-10 text-center transition-colors',
          dragActive
            ? 'border-primary bg-primary/5'
            : 'border-muted-foreground/30 hover:border-primary/50 hover:bg-muted/20',
        )}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
          <UploadCloud className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <p className="font-display font-semibold text-foreground">
            Kéo &amp; thả CV của bạn vào đây
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            hoặc nhấp để chọn tệp. Chỉ hỗ trợ PDF, tối đa 10MB.
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={handleFileInput}
        />
      </div>

      {fileName ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileText className="h-4 w-4" aria-hidden="true" />
          {fileName}
        </p>
      ) : null}

      {isUploading ? (
        <div className="flex items-center gap-3 rounded-xl border bg-muted/30 p-3 text-sm text-muted-foreground">
          <Spinner size="sm" />
          <span>Đang tải lên và phân tích CV của bạn...</span>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {error}
        </p>
      ) : null}

      {fileName ? (
        <Button
          type="button"
          variant="outline"
          onClick={() => inputRef.current?.click()}
          disabled={isUploading}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Chọn tệp khác
        </Button>
      ) : null}
    </div>
  )
}