import { Link } from 'react-router-dom'
import { MapPin, Building, Users } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  WORKPLACE_TYPE_LABELS,
} from '@/types/job'
import type { Job } from '@/types/job'

export interface RecruiterJobCardProps {
  job: Job
}

export function RecruiterJobCard({ job }: RecruiterJobCardProps) {
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
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="ai-gradient">{JOB_STATUS_LABELS[job.status]}</Badge>
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
      <CardFooter>
        <Link to={`/recruiter/jobs/${job.id}/applicants`} className="w-full">
          <Button variant="outline" className="w-full">
            <Users className="h-4 w-4" aria-hidden="true" />
            View applicants
          </Button>
        </Link>
      </CardFooter>
    </Card>
  )
}
