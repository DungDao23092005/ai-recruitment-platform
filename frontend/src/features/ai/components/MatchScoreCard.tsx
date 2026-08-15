import {
  CheckCircle2,
  XCircle,
  Lightbulb,
  Sparkles,
} from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { ScoreRing } from '@/components/ui/score-ring'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { cn } from '@/utils/cn'
import type { MatchResult, ParsedJob, ParsedResume } from '@/types/ai'
import { ExplainMatchModal } from './ExplainMatchModal'

export interface MatchScoreCardProps {
  matchResult: MatchResult
  candidate?: ParsedResume | null
  job?: ParsedJob | null
  className?: string
}

export function getScoreColor(score: number): {
  text: string
  bar: string
  progress: 'success' | 'warning' | 'danger'
} {
  if (score >= 75) {
    return { text: 'text-success', bar: 'bg-success', progress: 'success' }
  }
  if (score >= 50) {
    return { text: 'text-warning', bar: 'bg-warning', progress: 'warning' }
  }
  return { text: 'text-destructive', bar: 'bg-destructive', progress: 'danger' }
}

export function matchLevelLabel(score: number): {
  label: string
  variant: 'success' | 'warning' | 'destructive'
} {
  if (score >= 75) {
    return { label: 'Rất phù hợp', variant: 'success' }
  }
  if (score >= 50) {
    return { label: 'Phù hợp trung bình', variant: 'warning' }
  }
  return { label: 'Ít phù hợp', variant: 'destructive' }
}

export function formatPercent(value: number): string {
  if (Number.isNaN(value)) {
    return '0%'
  }
  return `${Math.round(value * 100)}%`
}

export function MatchScoreCard({
  matchResult,
  candidate,
  job,
  className,
}: MatchScoreCardProps) {
  const [showExplain, setShowExplain] = useState(false)
  const overall = Math.round(matchResult.overall_score)
  const { text: scoreText } = getScoreColor(overall)
  const level = matchLevelLabel(overall)

  const breakdown = [
    {
      label: 'Độ tương đồng ngữ nghĩa',
      value: formatPercent(matchResult.cosine_similarity),
      raw: matchResult.cosine_similarity,
    },
    {
      label: 'Độ phủ kỹ năng',
      value: formatPercent(matchResult.skill_coverage_score),
      raw: matchResult.skill_coverage_score,
    },
    {
      label: 'Độ khớp kinh nghiệm',
      value: formatPercent(matchResult.experience_match_score),
      raw: matchResult.experience_match_score,
    },
  ]

  return (
    <Card className={cn('flex h-full flex-col', className)}>
      <CardHeader className="pb-4">
        <CardTitle className="font-display text-lg font-semibold">
          Điểm đối sánh
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        <div className="flex items-center gap-5">
          <ScoreRing
            value={overall}
            size={88}
            strokeWidth={7}
            label={`Điểm tổng thể ${overall} phần trăm`}
          />
          <div className="space-y-1">
            <p className={cn('font-display text-3xl font-bold', scoreText)}>
              {overall}%
            </p>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Điểm tổng thể
            </p>
            <Badge variant={level.variant}>{level.label}</Badge>
          </div>
        </div>

        <div className="space-y-3">
          {breakdown.map((item) => {
            const { progress } = getScoreColor(item.raw * 100)
            return (
              <div key={item.label}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{item.label}</span>
                  <span className="font-medium">{item.value}</span>
                </div>
                <Progress value={item.raw * 100} variant={progress} />
              </div>
            )
          })}
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <CheckCircle2
                className="h-4 w-4 text-success"
                aria-hidden="true"
              />
              Kỹ năng khớp
            </p>
            {matchResult.matching_skills.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {matchResult.matching_skills.map((skill) => (
                  <Badge key={skill} variant="success">
                    {skill}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Chưa có kỹ năng khớp nào.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <XCircle
                className="h-4 w-4 text-destructive"
                aria-hidden="true"
              />
              Khoảng cách kỹ năng
            </p>
            {matchResult.skill_gap.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {matchResult.skill_gap.map((skill) => (
                  <Badge key={skill} variant="destructive">
                    {skill}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Không phát hiện khoảng cách kỹ năng.
              </p>
            )}
          </div>
        </div>

        {matchResult.match_reasons.length > 0 ? (
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Lightbulb
                className="h-4 w-4 text-warning"
                aria-hidden="true"
              />
              Vì sao phù hợp
            </p>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {matchResult.match_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-auto w-full"
          onClick={() => setShowExplain(true)}
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Xem giải thích AI
        </Button>
      </CardContent>

      {showExplain ? (
        <ExplainMatchModal
          matchResult={matchResult}
          candidate={candidate}
          job={job}
          onClose={() => setShowExplain(false)}
        />
      ) : null}
    </Card>
  )
}