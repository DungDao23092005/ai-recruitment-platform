import { Link } from 'react-router-dom'
import { MapPin, Briefcase, Building } from 'lucide-react'
import type { Job } from '@/types/job'
import {
  JOB_TYPE_LABELS,
  WORKPLACE_TYPE_LABELS,
} from '@/types/job'
import {
  Card,
  CardContent,
  CardDescription,
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
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function JobCard({ job }: JobCardProps) {
  const postedDate = formatPostedDate(job.created_at)

  return (
    <Card className="flex h-full flex-col transition-shadow hover:shadow-md">
      <CardHeader>
        <CardTitle className="text-lg">{job.title}</CardTitle>
        <CardDescription className="flex items-center gap-1">
          <Building className="h-4 w-4" aria-hidden="true" />
          <span className="text-xs uppercase text-muted-foreground">
            Company ID: {job.company_id.slice(0, 8)}
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 space-y-3">
        <p className="line-clamp-3 text-sm text-muted-foreground">
          {job.description}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="neutral">{JOB_TYPE_LABELS[job.job_type]}</Badge>
          <Badge variant="neutral">{WORKPLACE_TYPE_LABELS[job.workplace_type]}</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            {job.location}
          </span>
          {postedDate ? (
            <span className="text-xs">Posted {postedDate}</span>
          ) : null}
        </div>
      </CardContent>
      <CardFooter>
        <Link to={`/jobs/${job.id}`} className="w-full">
          <Button variant="outline" className="w-full">
            <Briefcase className="h-4 w-4" aria-hidden="true" />
            View details
          </Button>
        </Link>
      </CardFooter>
    </Card>
  )
}