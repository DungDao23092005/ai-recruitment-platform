import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { useJobs } from './useJobs'
import * as jobsApi from '@/api/jobs'

// Mock the API module
vi.mock('@/api/jobs', () => ({
  getJobs: vi.fn(),
}))

function renderHookWithRouter(hook: () => ReturnType<typeof useJobs>, initialEntries: string[] = ['/jobs']) {
  return renderHook(() => hook(), {
    wrapper: ({ children }) => <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>,
  })
}

describe('useJobs', () => {
  const mockGetJobs = vi.mocked(jobsApi.getJobs)

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('Test 1 - Valid empty response: verify jobs becomes []', async () => {
    mockGetJobs.mockResolvedValueOnce({ items: [], total: 0 })

    const { result } = renderHookWithRouter(() => useJobs())

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

    const { result } = renderHookWithRouter(() => useJobs())

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

    const { result } = renderHookWithRouter(() => useJobs())

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

    const { result } = renderHookWithRouter(() => useJobs())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.jobs).toEqual([])
    expect(result.current.error).toBe('Invalid API response format (expected JSON object with items array).')
  })

  it('Test 5 - Network/API failure: verify the existing error state is rendered', async () => {
    mockGetJobs.mockRejectedValueOnce(new Error('Network Error'))

    const { result } = renderHookWithRouter(() => useJobs())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.jobs).toEqual([])
    expect(result.current.error).toBe('Network Error')
  })

  // UI-03 Regression Tests: URL query param handling
  it('reads keyword from URL query param (q) on mount', async () => {
    const mockJobs = [
      { id: '1', title: 'Python Developer', company_id: 'c1', description: 'desc', status: 'published', job_type: 'full_time', workplace_type: 'remote', location: 'VN', created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    ]
    // @ts-ignore
    mockGetJobs.mockResolvedValueOnce({ items: mockJobs, total: 1 })

    // Render with URL containing ?q=python
    const { result } = renderHookWithRouter(() => useJobs(), ['/jobs?q=python'])

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Verify the keyword filter was initialized from URL
    expect(result.current.filters.keyword).toBe('python')
    // Verify API was called with the keyword
    expect(mockGetJobs).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: 'python' })
    )
  })

  it('reads Vietnamese keyword from URL query param on mount', async () => {
    const mockJobs = [
      { id: '1', title: 'Lập trình viên Python', company_id: 'c1', description: 'desc', status: 'published', job_type: 'full_time', workplace_type: 'remote', location: 'VN', created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    ]
    // @ts-ignore
    mockGetJobs.mockResolvedValueOnce({ items: mockJobs, total: 1 })

    // Render with URL containing Vietnamese keyword
    const { result } = renderHookWithRouter(() => useJobs(), ['/jobs?q=l%E1%BA%ADp%20tr%C3%ACnh%20vi%C3%AAn'])

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Verify the keyword filter was initialized from URL (decoded)
    expect(result.current.filters.keyword).toBe('lập trình viên')
    // Verify API was called with the decoded keyword
    expect(mockGetJobs).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: 'lập trình viên' })
    )
  })

  it('handles empty keyword from URL query param', async () => {
    mockGetJobs.mockResolvedValueOnce({ items: [], total: 0 })

    // Render with URL containing empty q param
    const { result } = renderHookWithRouter(() => useJobs(), ['/jobs?q='])

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.filters.keyword).toBe('')
    expect(mockGetJobs).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: undefined })
    )
  })

  it('handles whitespace-only keyword from URL query param', async () => {
    mockGetJobs.mockResolvedValueOnce({ items: [], total: 0 })

    // Render with URL containing whitespace-only q param
    const { result } = renderHookWithRouter(() => useJobs(), ['/jobs?q=%20%20'])

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.filters.keyword).toBe('  ')
    expect(mockGetJobs).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: '  ' })
    )
  })

  it('refresh preserves keyword from URL query param', async () => {
    const mockJobs = [
      { id: '1', title: 'Python Developer', company_id: 'c1', description: 'desc', status: 'published', job_type: 'full_time', workplace_type: 'remote', location: 'VN', created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    ]
    // @ts-ignore
    mockGetJobs.mockResolvedValueOnce({ items: mockJobs, total: 1 })

    const { result } = renderHookWithRouter(() => useJobs(), ['/jobs?q=python'])

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Verify initial keyword
    expect(result.current.filters.keyword).toBe('python')

    // Call refresh
    mockGetJobs.mockResolvedValueOnce({ items: mockJobs, total: 1 })
    result.current.refresh()

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Verify keyword is preserved and API called with keyword again
    expect(result.current.filters.keyword).toBe('python')
    expect(mockGetJobs).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: 'python' })
    )
  })

  it('Enter submit from homepage navigates to URL with keyword and useJobs reads it', async () => {
    const mockJobs = [
      { id: '1', title: 'Python Developer', company_id: 'c1', description: 'desc', status: 'published', job_type: 'full_time', workplace_type: 'remote', location: 'VN', created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    ]
    // @ts-ignore
    mockGetJobs.mockResolvedValueOnce({ items: mockJobs, total: 1 })

    // Simulate the flow: HomePage submits form -> navigates to /jobs?q=python
    // Then useJobs is mounted with that URL
    const { result } = renderHookWithRouter(() => useJobs(), ['/jobs?q=python'])

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.filters.keyword).toBe('python')
    expect(mockGetJobs).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: 'python' })
    )
  })
})
