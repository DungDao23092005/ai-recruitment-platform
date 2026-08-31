import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useJobs } from './useJobs'
import * as jobsApi from '@/api/jobs'

// Mock the API module
vi.mock('@/api/jobs', () => ({
  getJobs: vi.fn(),
}))

describe('useJobs', () => {
  const mockGetJobs = vi.mocked(jobsApi.getJobs)

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('Test 1 - Valid empty response: verify jobs becomes []', async () => {
    mockGetJobs.mockResolvedValueOnce({ items: [], total: 0 })

    const { result } = renderHook(() => useJobs())

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.jobs).toEqual([])
    expect(result.current.total).toBe(0)
    expect(result.current.error).toBeNull()
  })

  it('Test 2 - Valid jobs: verify jobs is an array', async () => {
    const mockJobs = [
      { id: '1', title: 'Software Engineer', company_id: 'c1', description: 'desc', status: 'published', job_type: 'full_time', workplace_type: 'remote', location: 'VN', created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    ]
    // @ts-ignore - mock partial job object for testing
    mockGetJobs.mockResolvedValueOnce({ items: mockJobs, total: 1 })

    const { result } = renderHook(() => useJobs())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.jobs).toHaveLength(1)
    expect(result.current.jobs[0].id).toBe('1')
    expect(result.current.total).toBe(1)
    expect(result.current.error).toBeNull()
  })

  it('Test 3 - Malformed response: verify the hook enters the error state and does not crash', async () => {
    // Return an object that is missing 'items'
    // @ts-ignore
    mockGetJobs.mockResolvedValueOnce({ total: 1 })

    const { result } = renderHook(() => useJobs())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.jobs).toEqual([]) // Should remain the initial []
    expect(result.current.error).toBe('Invalid API response format (expected JSON object with items array).')
  })

  it('Test 4 - HTML response: verify the hook handles it safely', async () => {
    // Simulate API returning an HTML string (e.g. from an SPA rewrite fallback)
    // @ts-ignore
    mockGetJobs.mockResolvedValueOnce('<!doctype html><html><body>Error</body></html>')

    const { result } = renderHook(() => useJobs())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.jobs).toEqual([])
    expect(result.current.error).toBe('Invalid API response format (expected JSON object with items array).')
  })

  it('Test 5 - Network/API failure: verify the existing error state is rendered', async () => {
    mockGetJobs.mockRejectedValueOnce(new Error('Network Error'))

    const { result } = renderHook(() => useJobs())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.jobs).toEqual([])
    expect(result.current.error).toBe('Network Error')
  })
})
