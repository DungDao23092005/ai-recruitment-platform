import { Link } from 'react-router-dom'
import { MapPin, Building, ArrowRight, CalendarDays } from 'lucide-react'
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
import { Button } from '@/components/ui/button'

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

export function JobCard({ job }: JobCardProps) {
  const postedDate = formatPostedDate(job.created_at)

  return (
    <Card className="group flex h-full flex-col border-border/70 bg-card transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft">
      <CardHeader className="gap-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="font-display text-lg font-semibold leading-snug text-foreground">
            {job.title}
          </CardTitle>
        </div>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Building className="h-4 w-4 text-primary/70" aria-hidden="true" />
          Công ty {job.company_name ?? job.company_id.slice(0, 8)}
        </p>
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
        <Link to={`/jobs/${job.id}`} className="w-full">
          <Button
            variant="outline"
            className="group-hover:border-primary/40 group-hover:text-primary"
          >
            Xem chi tiết
            <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
          </Button>
        </Link>
      </CardFooter>
    </Card>
  )
}