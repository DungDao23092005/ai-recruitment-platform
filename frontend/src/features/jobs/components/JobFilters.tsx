import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import type { JobFiltersState } from '@/features/jobs/hooks/useJobs'
import type { JobType, WorkplaceType } from '@/types/job'
import { JOB_TYPE_LABELS, WORKPLACE_TYPE_LABELS } from '@/types/job'

export interface JobFiltersProps {
  filters: JobFiltersState
  onKeywordChange: (value: string) => void
  onWorkplaceTypeChange: (value: WorkplaceType | '') => void
  onJobTypeChange: (value: JobType | '') => void
  onLocationChange: (value: string) => void
  onClear?: () => void
}

function hasActiveFilters(filters: JobFiltersState): boolean {
  return Boolean(
    filters.keyword ||
      filters.workplace_type ||
      filters.job_type ||
      filters.location,
  )
}

export function JobFilters({
  filters,
  onKeywordChange,
  onWorkplaceTypeChange,
  onJobTypeChange,
  onLocationChange,
  onClear,
}: JobFiltersProps) {
  const active = hasActiveFilters(filters)

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1.5">
          <label htmlFor="keyword" className="text-sm font-medium">
            Từ khóa
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              id="keyword"
              name="keyword"
              className="pl-9"
              placeholder="Tìm theo tên công việc..."
              value={filters.keyword}
              onChange={(e) => onKeywordChange(e.target.value)}
            />
          </div>
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
      {active && onClear ? (
        <div className="mt-4 flex items-center justify-between border-t pt-4">
          <p className="text-sm text-muted-foreground">
            Bộ lọc đang áp dụng
          </p>
          <Button variant="ghost" size="sm" onClick={onClear}>
            <X className="h-4 w-4" aria-hidden="true" />
            Xóa bộ lọc
          </Button>
        </div>
      ) : null}
    </div>
  )
}