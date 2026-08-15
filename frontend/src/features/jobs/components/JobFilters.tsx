import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import type { JobFiltersState } from '@/features/jobs/hooks/useJobs'
import type { JobType, WorkplaceType } from '@/types/job'
import { JOB_TYPE_LABELS, WORKPLACE_TYPE_LABELS } from '@/types/job'

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
    <div className="grid gap-4 rounded-xl border bg-card p-4 shadow-sm md:grid-cols-2 lg:grid-cols-4">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-9 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          name="keyword"
          label="Từ khóa"
          className="pl-9"
          placeholder="Tìm theo tên công việc..."
          value={filters.keyword}
          onChange={(e) => onKeywordChange(e.target.value)}
        />
      </div>
      <Select
        id="workplace-type"
        name="workplace_type"
        label="Hình thức làm việc"
        value={filters.workplace_type}
        onChange={(e) =>
          onWorkplaceTypeChange(e.target.value as WorkplaceType | '')
        }
      >
        <option value="">Tất cả hình thức</option>
        {Object.entries(WORKPLACE_TYPE_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </Select>
      <Select
        id="job-type"
        name="job_type"
        label="Loại công việc"
        value={filters.job_type}
        onChange={(e) => onJobTypeChange(e.target.value as JobType | '')}
      >
        <option value="">Tất cả loại công việc</option>
        {Object.entries(JOB_TYPE_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </Select>
      <Input
        id="location"
        name="location"
        label="Địa điểm"
        placeholder="Thành phố, Quốc gia..."
        value={filters.location}
        onChange={(e) => onLocationChange(e.target.value)}
      />
    </div>
  )
}