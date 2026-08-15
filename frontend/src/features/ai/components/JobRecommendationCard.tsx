import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  MatchScoreCard,
  getScoreColor,
} from '@/features/ai/components/MatchScoreCard'
import { cn } from '@/utils/cn'
import type { JobMatchRecommendation } from '@/types/ai'

export interface JobRecommendationCardProps {
  recommendation: JobMatchRecommendation
}

export function JobRecommendationCard({
  recommendation,
}: JobRecommendationCardProps) {
  const { job_id, parsed_job, match_result } = recommendation
  const overall = Math.round(match_result.overall_score)
  const { text: scoreText } = getScoreColor(overall)

  const title = parsed_job?.title ?? 'Chưa có tên công việc'
  const summary = parsed_job?.summary

  return (
    <Card className="flex h-full flex-col border-border/70 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft">
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="font-display text-lg font-semibold leading-snug">
            {title}
          </CardTitle>
          <Badge
            variant="neutral"
            className={cn('shrink-0 font-bold', scoreText)}
            aria-label={`Điểm đối sánh ${overall} phần trăm`}
          >
            {overall}%
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex-1 space-y-4">
        {summary ? (
          <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground">
            {summary}
          </p>
        ) : null}

        {match_result.matching_skills.length > 0 ? (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Kỹ năng khớp
            </p>
            <div className="flex flex-wrap gap-1.5">
              {match_result.matching_skills.map((skill) => (
                <Badge key={skill} variant="success">
                  {skill}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {match_result.skill_gap.length > 0 ? (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Khoảng cách kỹ năng
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
            <MatchScoreCard matchResult={match_result} job={parsed_job} />
          </div>
        </details>
      </CardContent>
      <CardFooter>
        <Link to={`/jobs/${job_id}`} className="w-full">
          <Button className="w-full">
            Xem chi tiết &amp; Nộp đơn
          </Button>
        </Link>
      </CardFooter>
    </Card>
  )
}