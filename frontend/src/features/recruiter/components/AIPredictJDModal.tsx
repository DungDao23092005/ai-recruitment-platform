import { useState, type FormEvent } from 'react'
import { Sparkles } from 'lucide-react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Spinner } from '@/components/ui/spinner'
import { Modal } from '@/components/ui/modal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { Badge } from '@/components/ui/badge'

export interface ParsedJob {
  title: string | null
  summary: string | null
  required_skills: string[]
  preferred_skills: string[]
  minimum_years_experience: number | null
  education_level: string | null
}

export interface AIPredictJDModalProps {
  onClose: () => void
  onApply?: (parsed: ParsedJob) => void
}

export function AIPredictJDModal({ onClose, onApply }: AIPredictJDModalProps) {
  const [jobTitle, setJobTitle] = useState('')
  const [rawJd, setRawJd] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [parsed, setParsed] = useState<ParsedJob | null>(null)

  const handleParse = async (event: FormEvent) => {
    event.preventDefault()
    if (!rawJd.trim()) {
      setError('Vui lòng dán mô tả công việc trước.')
      return
    }
    setIsLoading(true)
    setError(null)
    setParsed(null)
    try {
      const result = await apiClient.post<ParsedJob, ParsedJob>(
        '/ai/parse-jd',
        {
          job_title: jobTitle.trim(),
          job_description: rawJd,
          job_id: null,
        },
      )
      setParsed(result)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      ariaLabel="AI phân tích JD"
      size="lg"
      title={
        <span className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
          AI phân tích JD
        </span>
      }
      description="Dán mô tả công việc của bạn và để AI trích xuất kỹ năng cùng yêu cầu."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            Đóng
          </Button>
          <Button
            disabled={!parsed}
            onClick={() => {
              if (parsed) onApply?.(parsed)
            }}
          >
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            Áp dụng vào tin tuyển dụng
          </Button>
        </>
      }
    >
      <form onSubmit={handleParse} className="space-y-4" noValidate>
        <Input
          name="job_title"
          label="Tiêu đề công việc (tùy chọn)"
          placeholder="Kỹ sư Frontend cấp cao"
          value={jobTitle}
          onChange={(e) => setJobTitle(e.target.value)}
        />
        <Textarea
          name="job_description"
          label="Mô tả công việc"
          rows={8}
          value={rawJd}
          onChange={(e) => setRawJd(e.target.value)}
          placeholder="Dán toàn bộ mô tả công việc vào đây..."
        />

        <Button
          type="submit"
          disabled={isLoading}
          isLoading={isLoading}
          loadingText="Đang phân tích JD..."
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Phân tích JD bằng AI
        </Button>

        {error ? (
          <p role="alert" className="text-sm font-medium text-destructive">
            {error}
          </p>
        ) : null}

        {isLoading ? (
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Spinner size="sm" />
            <span>Đang phân tích JD bằng AI...</span>
          </div>
        ) : null}

        {parsed ? (
          <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
            {parsed.title ? (
              <p className="text-sm">
                <span className="font-medium">Tiêu đề: </span>
                {parsed.title}
              </p>
            ) : null}
            {parsed.summary ? (
              <p className="text-sm">
                <span className="font-medium">Tóm tắt: </span>
                {parsed.summary}
              </p>
            ) : null}
            {parsed.required_skills.length > 0 ? (
              <div className="space-y-1">
                <p className="text-sm font-medium">Kỹ năng bắt buộc</p>
                <div className="flex flex-wrap gap-2">
                  {parsed.required_skills.map((skill) => (
                    <Badge key={skill} variant="neutral">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
            {parsed.preferred_skills.length > 0 ? (
              <div className="space-y-1">
                <p className="text-sm font-medium">Kỹ năng mong muốn</p>
                <div className="flex flex-wrap gap-2">
                  {parsed.preferred_skills.map((skill) => (
                    <Badge key={skill} variant="warning">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
            {parsed.minimum_years_experience != null ? (
              <p className="text-sm">
                <span className="font-medium">Kinh nghiệm tối thiểu: </span>
                {parsed.minimum_years_experience} năm
              </p>
            ) : null}
            {parsed.education_level ? (
              <p className="text-sm">
                <span className="font-medium">Trình độ học vấn: </span>
                {parsed.education_level}
              </p>
            ) : null}
          </div>
        ) : null}
      </form>
    </Modal>
  )
}