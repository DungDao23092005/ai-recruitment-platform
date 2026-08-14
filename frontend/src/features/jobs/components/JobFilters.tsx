import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import type { JobFiltersState } from '@/features/jobs/hooks/useJobs'
import type { JobType, WorkplaceType } from '@/types/job'

export interface JobFiltersProps {
  filters: JobFiltersState
  onKeywordChange: (value: string) => void
  onWorkplaceTypeChange: (value: WorkplaceType | '') => void
  onJobTypeChange: (value: JobType | '') => void
  onLocationChange: (value: string) => void
}

export function JobFilters({
  filters,
  onKeywordChange,
  onWorkplaceTypeChange,
  onJobTypeChange,
  onLocationChange,
}: JobFiltersProps) {
  return (
    <div className="grid gap-4 rounded-lg border bg-muted/20 p-4 md:grid-cols-2 lg:grid-cols-4">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          name="keyword"
          label="Keyword"
          className="pl-9"
          placeholder="Search job title..."
          value={filters.keyword}
          onChange={(e) => onKeywordChange(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="workplace-type"
          className="text-sm font-medium leading-none"
        >
          Workplace type
        </label>
        <select
          id="workplace-type"
          name="workplace_type"
          value={filters.workplace_type}
          onChange={(e) =>
            onWorkplaceTypeChange(e.target.value as WorkplaceType | '')
          }
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <option value="">All workplace types</option>
          <option value="on_site">On-site</option>
          <option value="hybrid">Hybrid</option>
          <option value="remote">Remote</option>
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="job-type" className="text-sm font-medium leading-none">
          Job type
        </label>
        <select
          id="job-type"
          name="job_type"
          value={filters.job_type}
          onChange={(e) =>
            onJobTypeChange(e.target.value as JobType | '')
          }
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <option value="">All job types</option>
          <option value="full_time">Full time</option>
          <option value="part_time">Part time</option>
          <option value="contract">Contract</option>
          <option value="internship">Internship</option>
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="location" className="text-sm font-medium leading-none">
          Location
        </label>
        <Input
          id="location"
          name="location"
          placeholder="City, Country..."
          value={filters.location}
          onChange={(e) => onLocationChange(e.target.value)}
        />
      </div>
    </div>
  )
}