import { useCallback, useEffect, useState } from 'react'
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
  total: number
  setKeyword: (value: string) => void
  setWorkplaceType: (value: WorkplaceType | '') => void
  setJobType: (value: JobType | '') => void
  setLocation: (value: string) => void
  clearFilters: () => void
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
  const [total, setTotal] = useState(0)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getJobs({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        keyword: filters.keyword || undefined,
        workplace_type: filters.workplace_type || undefined,
        job_type: filters.job_type || undefined,
        location: filters.location || undefined,
      })
      setJobs(data.items)
      setTotal(data.total)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unable to load jobs'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }, [page, filters])

  useEffect(() => {
    void load()
  }, [load])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

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

  const clearFilters = useCallback(() => {
    setFilters({
      keyword: '',
      workplace_type: '',
      job_type: '',
      location: '',
    })
    setPage(1)
  }, [])

  const refresh = useCallback(() => {
    void load()
  }, [load])

  // Reset page to 1 when filters change
  useEffect(() => {
    setPage(1)
  }, [filters.keyword, filters.workplace_type, filters.job_type, filters.location])

  return {
    jobs,
    isLoading,
    error,
    filters,
    page,
    totalPages,
    total,
    setKeyword,
    setWorkplaceType,
    setJobType,
    setLocation,
    clearFilters,
    goToPage,
    refresh,
  }
}