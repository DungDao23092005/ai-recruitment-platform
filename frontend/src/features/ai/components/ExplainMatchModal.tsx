import { useEffect, useState } from 'react'
import { Sparkles, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Modal } from '@/components/ui/modal'
import { Spinner } from '@/components/ui/spinner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { explainMatch } from '@/api/ai'
import type {
  ExplainMatchResponse,
  MatchResult,
  ParsedJob,
  ParsedResume,
} from '@/types/ai'

export interface ExplainMatchModalProps {
  matchResult: MatchResult
  candidate?: ParsedResume | null
  job?: ParsedJob | null
  onClose: () => void
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="font-display text-sm font-semibold text-foreground">
        {title}
      </p>
      {children}
    </div>
  )
}

export function ExplainMatchModal({
  matchResult,
  candidate,
  job,
  onClose,
}: ExplainMatchModalProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [explanation, setExplanation] = useState<ExplainMatchResponse | null>(
    null,
  )

  const loadExplanation = async () => {
    setIsLoading(true)
    setError(null)
    setExplanation(null)
    try {
      const result = await explainMatch({
        match_result: matchResult,
        candidate: candidate ?? null,
        job: job ?? null,
      })
      setExplanation(result)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void loadExplanation()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Modal
      onClose={onClose}
      size="lg"
      ariaLabel="Giải Thích Chi Tiết Độ Phù Hợp Bằng AI"
      title={
        <span className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
          Giải Thích Chi Tiết Độ Phù Hợp Bằng AI
        </span>
      }
      description="Gemini giải thích kết quả đối sánh dựa trên dữ kiện đã được cung cấp."
      footer={
        <Button variant="ghost" onClick={onClose} disabled={isLoading}>
          Đóng
        </Button>
      }
    >
      <div className="space-y-5">
        {isLoading ? (
          <div className="flex items-center gap-3 rounded-xl border bg-muted/30 p-4 text-sm text-muted-foreground">
            <Spinner size="sm" />
            <span>Gemini AI đang phân tích dữ liệu đối sánh...</span>
          </div>
        ) : null}

        {error ? (
          <div role="alert" className="space-y-3">
            <p className="text-sm font-medium text-destructive">{error}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={loadExplanation}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Thử lại
            </Button>
          </div>
        ) : null}

        {explanation ? (
          <div className="space-y-5">
            <Section title="Tóm tắt">
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                {explanation.summary}
              </p>
            </Section>

            <Section title="Điểm mạnh">
              {explanation.strengths.length > 0 ? (
                <ul className="mt-1 list-inside list-disc space-y-1 text-sm text-muted-foreground">
                  {explanation.strengths.map((strength) => (
                    <li key={strength}>{strength}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-muted-foreground">
                  Không xác định được điểm mạnh.
                </p>
              )}
            </Section>

            <Section title="Khoảng cách kỹ năng">
              {explanation.skill_gaps.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {explanation.skill_gaps.map((skill) => (
                    <Badge key={skill} variant="destructive">
                      {skill}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="mt-1 text-sm text-muted-foreground">
                  Không phát hiện khoảng cách kỹ năng.
                </p>
              )}
            </Section>

            <Section title="Phân tích kinh nghiệm">
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                {explanation.experience_analysis}
              </p>
            </Section>

            <Section title="Đề xuất">
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                {explanation.recommendation}
              </p>
            </Section>
          </div>
        ) : null}
      </div>
    </Modal>
  )
}