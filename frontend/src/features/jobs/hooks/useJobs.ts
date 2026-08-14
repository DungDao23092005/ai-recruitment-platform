import { useCallback, useEffect, useMemo, useState } from 'react'
import { getJobs } from '@/api/jobs'
import type { Job, JobType, WorkplaceType } from '@/types/job'

export interface JobFiltersState {
  keyword: string
  workplace_type: WorkplaceType | ''
  job_type: JobType | ''
  location: string
}

export const PAGE_SIZE = 10

export interface UseJobsResult {
  jobs: Job[]
  isLoading: boolean
  error: string | null
  filters: JobFiltersState
  page: number
  totalPages: number
  setKeyword: (value: string) => void
  setWorkplaceType: (value: WorkplaceType | '') => void
  setJobType: (value: JobType | '') => void
  setLocation: (value: string) => void
  goToPage: (page: number) => void
  refresh: () => void
}

export function useJobs(): UseJobsResult {
  const [jobs, setJobs] = useState<Job[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<JobFiltersState>({
    keyword: '',
    workplace_type: '',
    job_type: '',
    location: '',
  })
  const [page, setPage] = useState(1)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getJobs({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      })
      setJobs(data)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unable to load jobs'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }, [page])

  useEffect(() => {
    void load()
  }, [load])

  const filteredJobs = useMemo(() => {
    const keyword = filters.keyword.trim().toLowerCase()
    const location = filters.location.trim().toLowerCase()

    return jobs.filter((job) => {
      if (
        filters.workplace_type &&
        job.workplace_type !== filters.workplace_type
      ) {
        return false
      }
      if (filters.job_type && job.job_type !== filters.job_type) {
        return false
      }
      if (keyword && !job.title.toLowerCase().includes(keyword)) {
        return false
      }
      if (location && !job.location.toLowerCase().includes(location)) {
        return false
      }
      return true
    })
  }, [jobs, filters])

  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / PAGE_SIZE))

  const setKeyword = useCallback((value: string) => {
    setFilters((f) => ({ ...f, keyword: value }))
  }, [])

  const setWorkplaceType = useCallback((value: WorkplaceType | '') => {
    setFilters((f) => ({ ...f, workplace_type: value }))
  }, [])

  const setJobType = useCallback((value: JobType | '') => {
    setFilters((f) => ({ ...f, job_type: value }))
  }, [])

  const setLocation = useCallback((value: string) => {
    setFilters((f) => ({ ...f, location: value }))
  }, [])

  const goToPage = useCallback((nextPage: number) => {
    setPage(nextPage)
  }, [])

  const refresh = useCallback(() => {
    void load()
  }, [load])

  return {
    jobs: filteredJobs,
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
    refresh,
  }
}