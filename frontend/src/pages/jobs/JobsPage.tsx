import { JobFilters } from '@/features/jobs/components/JobFilters'
import { JobList } from '@/features/jobs/components/JobList'
import { useJobs } from '@/features/jobs/hooks/useJobs'
import { PageHeader } from '@/components/common/PageHeader'

export interface JobsPageProps {
  detailPath?: string
  contained?: boolean
}

export function JobsPage({ detailPath = '/jobs', contained = true }: JobsPageProps) {
  const {
    jobs,
    isLoading,
    error,
    filters,
    page,
    totalPages,
    setKeyword,
    setWorkplaceType,
    setJobType,
    setLocation,
    clearFilters,
    goToPage,
  } = useJobs()

  return (
    <div className={contained ? 'container py-10 sm:py-12' : 'space-y-6'}>
      <PageHeader
        title="Việc làm"
        description="Khám phá cơ hội nghề nghiệp được tuyển chọn dành riêng cho bạn."
      />

      <div className="space-y-6">
        <JobFilters
          filters={filters}
          onKeywordChange={setKeyword}
          onWorkplaceTypeChange={setWorkplaceType}
          onJobTypeChange={setJobType}
          onLocationChange={setLocation}
          onClear={clearFilters}
        />
        <JobList
          jobs={jobs}
          isLoading={isLoading}
          error={error}
          page={page}
          totalPages={totalPages}
          onPageChange={goToPage}
          detailPath={detailPath}
        />
      </div>
    </div>
  )
}