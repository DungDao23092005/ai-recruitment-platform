import { useEffect, useState } from 'react'
import { Sparkles, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Giải Thích Chi Tiết Độ Phù Hợp Bằng AI"
      onClick={onClose}
    >
      <div
        className="flex max-h-full w-full max-w-2xl flex-col overflow-hidden rounded-lg border bg-background shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b p-5">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
            Giải Thích Chi Tiết Độ Phù Hợp Bằng AI
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Gemini giải thích kết quả đối sánh dựa trên dữ kiện đã được cung cấp.
          </p>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {isLoading ? (
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
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
              <div>
                <p className="text-sm font-medium">Summary</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {explanation.summary}
                </p>
              </div>

              <div>
                <p className="text-sm font-medium">Strengths</p>
                {explanation.strengths.length > 0 ? (
                  <ul className="mt-1 list-inside list-disc space-y-1 text-sm text-muted-foreground">
                    {explanation.strengths.map((strength) => (
                      <li key={strength}>{strength}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-sm text-muted-foreground">
                    No strengths identified.
                  </p>
                )}
              </div>

              <div>
                <p className="text-sm font-medium">Skill Gaps</p>
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
                    No skill gaps detected.
                  </p>
                )}
              </div>

              <div>
                <p className="text-sm font-medium">Experience Analysis</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {explanation.experience_analysis}
                </p>
              </div>

              <div>
                <p className="text-sm font-medium">Recommendation</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {explanation.recommendation}
                </p>
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-2 border-t p-4">
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            Close
          </Button>
        </div>
      </div>
    </div>
  )
}
