import { JobFilters } from '@/features/jobs/components/JobFilters'
import { JobList } from '@/features/jobs/components/JobList'
import { useJobs } from '@/features/jobs/hooks/useJobs'
import { PageHeader } from '@/components/common/PageHeader'

export function JobsPage() {
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
    goToPage,
  } = useJobs()

  return (
    <div className="container py-10">
      <PageHeader
        title="Việc làm"
        description="Explore job opportunities tailored for you."
      />

      <div className="space-y-6">
        <JobFilters
          filters={filters}
          onKeywordChange={setKeyword}
          onWorkplaceTypeChange={setWorkplaceType}
          onJobTypeChange={setJobType}
          onLocationChange={setLocation}
        />
        <JobList
          jobs={jobs}
          isLoading={isLoading}
          error={error}
          page={page}
          totalPages={totalPages}
          onPageChange={goToPage}
        />
      </div>
    </div>
  )
}