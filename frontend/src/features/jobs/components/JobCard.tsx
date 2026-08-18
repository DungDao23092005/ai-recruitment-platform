import { Link } from 'react-router-dom'
import { MapPin, ArrowRight, CalendarDays } from 'lucide-react'
import type { Job } from '@/types/job'
import { JOB_TYPE_LABELS, WORKPLACE_TYPE_LABELS } from '@/types/job'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/utils/cn'

export interface JobCardProps {
  job: Job
}

function formatPostedDate(dateString: string): string {
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleDateString('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
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

export function JobCard({ job }: JobCardProps) {
  const postedDate = formatPostedDate(job.created_at)
  const rawCompanyName = job.company_name ?? `Công ty ${job.company_id.slice(0, 8)}`
  const companyLabel = job.company_name
    ? `Công ty ${job.company_name}`
    : rawCompanyName

  return (
    <Card className="group flex h-full flex-col border-border/70 bg-card transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft">
      <CardHeader className="gap-2.5">
        <div className="flex items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 font-display text-sm font-bold text-primary ring-1 ring-primary/15"
            aria-hidden="true"
          >
            {companyMonogram(rawCompanyName)}
          </div>
          <div className="min-w-0 flex-1">
            <CardTitle className="line-clamp-1 font-display text-lg font-semibold leading-snug text-foreground">
              {job.title}
            </CardTitle>
            <p className="mt-0.5 truncate text-sm text-muted-foreground">
              {companyLabel}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 space-y-3">
        <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground">
          {job.description}
        </p>
        <div className="flex flex-wrap items-center gap-2">
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
          {postedDate ? (
            <span className="flex items-center gap-1 text-xs">
              <CalendarDays className="h-3.5 w-3.5" aria-hidden="true" />
              Đăng {postedDate}
            </span>
          ) : null}
        </div>
      </CardContent>
      <CardFooter>
        <Link
          to={`/jobs/${job.id}`}
          className={cn(
            buttonVariants({ variant: 'outline' }),
            'w-full group-hover:border-primary/40 group-hover:text-primary',
          )}
        >
          Xem chi tiết
          <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
        </Link>
      </CardFooter>
    </Card>
  )
}