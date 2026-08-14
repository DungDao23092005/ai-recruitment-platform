import { Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  MatchScoreCard,
  getScoreColor,
} from '@/features/ai/components/MatchScoreCard'
import { cn } from '@/utils/cn'
import type { CandidateMatchRecommendation } from '@/types/ai'

export interface CandidateRecommendationCardProps {
  recommendation: CandidateMatchRecommendation
}

function formatYearsExperience(value: number | null): string | null {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return null
  }
  return `${value} years`
}

export function CandidateRecommendationCard({
  recommendation,
}: CandidateRecommendationCardProps) {
  const { candidate_id, parsed_resume, match_result } = recommendation
  const overall = Math.round(match_result.overall_score)
  const { text: scoreText } = getScoreColor(overall)

  const fullName =
    parsed_resume?.full_name ?? `Candidate ${candidate_id.slice(0, 8)}`
  const title = parsed_resume?.title
  const experience = formatYearsExperience(
    parsed_resume?.total_years_experience ?? null,
  )
  const skills = parsed_resume?.skills ?? []

  return (
    <Card className="flex h-full flex-col transition-shadow hover:shadow-md">
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-lg">{fullName}</CardTitle>
          <Badge
            variant="neutral"
            className={cn('shrink-0 text-sm font-bold', scoreText)}
            aria-label={`Match score ${overall} percent`}
          >
            {overall}%
          </Badge>
        </div>
        {title ? (
          <CardDescription>{title}</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="flex-1 space-y-4">
        {experience ? (
          <p className="text-sm text-muted-foreground">
            {experience} experience
          </p>
        ) : null}

        {skills.length > 0 ? (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase text-muted-foreground">
              Skills
            </p>
            <div className="flex flex-wrap gap-1.5">
              {skills.map((skill) => (
                <Badge key={skill} variant="neutral">
                  {skill}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {match_result.skill_gap.length > 0 ? (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase text-muted-foreground">
              Skill gap
            </p>
            <div className="flex flex-wrap gap-1.5">
              {match_result.skill_gap.map((skill) => (
                <Badge key={skill} variant="destructive">
                  {skill}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        <details className="group">
          <summary className="flex cursor-pointer items-center gap-1.5 text-sm font-medium text-primary">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            Xem chi tiết Match Score
          </summary>
          <div className="mt-3">
            <MatchScoreCard
              matchResult={match_result}
              candidate={parsed_resume}
            />
          </div>
        </details>
      </CardContent>
    </Card>
  )
}