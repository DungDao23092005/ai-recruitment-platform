import type { Job } from '@/types/job'
import { JobCard } from '@/features/jobs/components/JobCard'
import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'

export interface JobListProps {
  jobs: Job[]
  isLoading: boolean
  error: string | null
  page: number
  totalPages: number
  onPageChange: (page: number) => void
}

export function JobList({
  jobs,
  isLoading,
  error,
  page,
  totalPages,
  onPageChange,
}: JobListProps) {
  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm font-medium text-destructive">{error}</p>
        <p className="text-sm text-muted-foreground">
          Unable to load jobs right now.
        </p>
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-center">
        <p className="text-sm text-muted-foreground">
          No jobs found. Try adjusting your filters.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {jobs.map((job) => (
          <JobCard key={job.id} job={job} />
        ))}
      </div>

      {totalPages > 1 ? (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </Button>
          <span className="px-2 text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </Button>
        </div>
      ) : null}
    </div>
  )
}