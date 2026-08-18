import { Link } from 'react-router-dom'
import {
  MapPin,
  Users,
  Sparkles,
  FileQuestion,
  ChevronRight,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { BadgeProps } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  WORKPLACE_TYPE_LABELS,
} from '@/types/job'
import type { Job, JobStatus } from '@/types/job'
import { cn } from '@/utils/cn'

export interface RecruiterJobCardProps {
  job: Job
}

function companyMonogram(companyName: string): string {
  const trimmed = companyName.trim()
  if (!trimmed) {
    return 'C'
  }
  const words = trimmed.split(/\s+/)
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase()
  }
  return (
    words
      .slice(0, 2)
      .map((word) => word[0])
      .join('')
      .toUpperCase()
  )
}

const JOB_STATUS_VARIANT: Record<JobStatus, NonNullable<BadgeProps['variant']>> = {
  draft: 'neutral',
  published: 'success',
  closed: 'warning',
  expired: 'destructive',
}

export function RecruiterJobCard({ job }: RecruiterJobCardProps) {
  const companyLabel = job.company_name
    ? `Công ty: ${job.company_name}`
    : `Công ty: ${job.company_id.slice(0, 8)}`

  return (
    <Card className="flex h-full flex-col border-border/70 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft">
      <CardHeader className="gap-2.5">
        <div className="flex items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 font-display text-sm font-bold text-primary ring-1 ring-primary/15"
            aria-hidden="true"
          >
            {companyMonogram(job.company_name ?? `Công ty ${job.company_id.slice(0, 8)}`)}
          </div>
          <div className="min-w-0 flex-1">
            <CardTitle className="line-clamp-1 font-display text-lg font-semibold text-foreground">
              {job.title}
            </CardTitle>
            <p className="mt-0.5 truncate text-sm text-muted-foreground">
              {companyLabel}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={JOB_STATUS_VARIANT[job.status]}>
            {JOB_STATUS_LABELS[job.status]}
          </Badge>
          <Badge variant="neutral">{JOB_TYPE_LABELS[job.job_type]}</Badge>
          <Badge variant="neutral">
            {WORKPLACE_TYPE_LABELS[job.workplace_type]}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            {job.location}
          </span>
        </div>
      </CardContent>
      <CardFooter className="flex-col gap-2">
        <Link
          to={`/recruiter/jobs/${job.id}/applicants`}
          className={cn(buttonVariants({ variant: 'outline' }), 'w-full')}
        >
          <Users className="h-4 w-4" aria-hidden="true" />
          Xem ứng viên
        </Link>
        <Link
          to={`/recruiter/jobs/${job.id}/recommendations`}
          className={cn(buttonVariants({ variant: 'outline' }), 'w-full')}
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Gợi ý ứng viên AI
        </Link>
        <Link
          to={`/recruiter/jobs/${job.id}/interview`}
          className={cn(buttonVariants({ variant: 'default' }), 'w-full')}
        >
          <FileQuestion className="h-4 w-4" aria-hidden="true" />
          Bộ câu hỏi phỏng vấn
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </CardFooter>
    </Card>
  )
}