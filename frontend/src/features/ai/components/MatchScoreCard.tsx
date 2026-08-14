import {
  CheckCircle2,
  XCircle,
  Lightbulb,
  Sparkles,
} from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
} {
  if (score >= 75) {
    return { text: 'text-emerald-600', bar: 'bg-emerald-500' }
  }
  if (score >= 50) {
    return { text: 'text-amber-600', bar: 'bg-amber-500' }
  }
  return { text: 'text-rose-600', bar: 'bg-rose-500' }
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
  const { text: scoreText, bar: scoreBar } = getScoreColor(overall)

  const breakdown = [
    {
      label: 'Cosine Similarity',
      value: formatPercent(matchResult.cosine_similarity),
      raw: matchResult.cosine_similarity,
    },
    {
      label: 'Skill Coverage',
      value: formatPercent(matchResult.skill_coverage_score),
      raw: matchResult.skill_coverage_score,
    },
    {
      label: 'Experience Match',
      value: formatPercent(matchResult.experience_match_score),
      raw: matchResult.experience_match_score,
    },
  ]

  return (
    <Card className={cn('flex h-full flex-col', className)}>
      <CardHeader className="pb-4">
        <CardTitle className="text-lg">Match Score</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        <div className="flex items-center gap-4">
          <div
            className={cn(
              'flex h-16 w-16 items-center justify-center rounded-full border-4 text-2xl font-bold',
              scoreText,
              scoreBar,
            )}
            aria-label={`Overall score ${overall} percent`}
          >
            {overall}%
          </div>
          <div className="space-y-1">
            <p className={cn('text-3xl font-bold', scoreText)}>{overall}%</p>
            <p className="text-xs uppercase text-muted-foreground">
              Overall Score
            </p>
          </div>
        </div>

        <div className="space-y-3">
          {breakdown.map((item) => {
            const { bar } = getScoreColor(item.raw * 100)
            return (
              <div key={item.label}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{item.label}</span>
                  <span className="font-medium">{item.value}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                  <div
                    className={cn('h-full rounded-full', bar)}
                    style={{
                      width: `${Math.min(100, Math.max(0, item.raw * 100))}%`,
                    }}
                  />
                </div>
              </div>
            )
          })}
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <CheckCircle2
                className="h-4 w-4 text-emerald-600"
                aria-hidden="true"
              />
              Matching Skills
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
                No matching skills found.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <XCircle className="h-4 w-4 text-rose-600" aria-hidden="true" />
              Skill Gap
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
                No skill gaps detected.
              </p>
            )}
          </div>
        </div>

        {matchResult.match_reasons.length > 0 ? (
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Lightbulb
                className="h-4 w-4 text-amber-500"
                aria-hidden="true"
              />
              Why this match
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
          className="w-full"
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