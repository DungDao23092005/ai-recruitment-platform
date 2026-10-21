import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMyApplications } from './useMyApplications'
import * as applicationsApi from '@/api/applications'
import type { ApplicationWithJob } from '@/types/application'

vi.mock('@/api/applications', () => ({
  getMyApplications: vi.fn(),
}))

const mockedGetMyApplications = vi.mocked(applicationsApi.getMyApplications)

const firstApplication: ApplicationWithJob = {
  id: 'app-1',
  job_id: 'job-1',
  job_title: 'Frontend Engineer',
  company_name: 'Acme',
  status: 'applied',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const updatedApplication: ApplicationWithJob = {
  ...firstApplication,
  status: 'shortlisted',
  updated_at: '2026-01-02T00:00:00Z',
}

function dispatchCandidatePipelineEvent() {
  window.dispatchEvent(
    new CustomEvent('candidate:pipeline:updated', {
      detail: { job_id: 'job-1', application_id: 'app-1' },
    }),
  )
}

describe('useMyApplications', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedGetMyApplications.mockResolvedValue([firstApplication])
  })

  it('loads the candidate applications on mount', async () => {
    const { result } = renderHook(() => useMyApplications())

    await waitFor(() => {
      expect(result.current.applications).toEqual([firstApplication])
    })
    expect(mockedGetMyApplications).toHaveBeenCalledWith({
      skip: 0,
      limit: 10,
    })
  })

  it('silently refreshes on candidate pipeline invalidation', async () => {
    const { result } = renderHook(() => useMyApplications())

    await waitFor(() => {
      expect(result.current.applications).toEqual([firstApplication])
    })

    mockedGetMyApplications.mockResolvedValue([updatedApplication])
    act(() => {
      dispatchCandidatePipelineEvent()
    })

    await waitFor(() => {
      expect(result.current.applications).toEqual([updatedApplication])
    })
    expect(mockedGetMyApplications).toHaveBeenCalledTimes(2)
  })

  it('keeps the current list visible while a silent refresh is in flight', async () => {
    const { result } = renderHook(() => useMyApplications())

    await waitFor(() => {
      expect(result.current.applications).toEqual([firstApplication])
    })

    let resolveRefresh!: (value: ApplicationWithJob[]) => void
    mockedGetMyApplications.mockReturnValue(
      new Promise((resolve) => {
        resolveRefresh = resolve
      }),
    )

    act(() => {
      dispatchCandidatePipelineEvent()
    })

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 300))
    })
    expect(result.current.isLoading).toBe(false)
    expect(result.current.applications).toEqual([firstApplication])

    act(() => {
      resolveRefresh([updatedApplication])
    })
    await waitFor(() => {
      expect(result.current.applications).toEqual([updatedApplication])
    })
  })

  it('debounces rapid candidate pipeline invalidations', async () => {
    const { result } = renderHook(() => useMyApplications())

    await waitFor(() => {
      expect(result.current.applications).toEqual([firstApplication])
    })

    mockedGetMyApplications.mockResolvedValue([updatedApplication])
    act(() => {
      dispatchCandidatePipelineEvent()
      dispatchCandidatePipelineEvent()
      dispatchCandidatePipelineEvent()
    })

    await waitFor(() => {
      expect(mockedGetMyApplications).toHaveBeenCalledTimes(2)
    })
  })

  it('refreshes after stream reconnect and visibility changes', async () => {
    const { result } = renderHook(() => useMyApplications())

    await waitFor(() => {
      expect(result.current.applications).toEqual([firstApplication])
    })

    act(() => {
      window.dispatchEvent(new CustomEvent('stream:connected'))
    })
    await waitFor(() => {
      expect(mockedGetMyApplications).toHaveBeenCalledTimes(2)
    })

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    })
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitFor(() => {
      expect(mockedGetMyApplications).toHaveBeenCalledTimes(3)
    })
  })

  it('ignores an older refresh response that resolves after a newer one', async () => {
    const { result } = renderHook(() => useMyApplications())

    await waitFor(() => {
      expect(result.current.applications).toEqual([firstApplication])
    })

    let resolveOlder!: (value: ApplicationWithJob[]) => void
    let resolveNewer!: (value: ApplicationWithJob[]) => void
    mockedGetMyApplications
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveOlder = resolve
        }),
      )
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveNewer = resolve
        }),
      )

    act(() => {
      result.current.refresh()
    })
    act(() => {
      result.current.refresh()
    })

    act(() => {
      resolveNewer([updatedApplication])
    })
    await waitFor(() => {
      expect(result.current.applications).toEqual([updatedApplication])
    })

    act(() => {
      resolveOlder([firstApplication])
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(result.current.applications).toEqual([updatedApplication])
  })

  it('keeps the existing list when a silent refresh fails', async () => {
    const { result } = renderHook(() => useMyApplications())

    await waitFor(() => {
      expect(result.current.applications).toEqual([firstApplication])
    })

    mockedGetMyApplications.mockRejectedValueOnce(new Error('Network error'))
    act(() => {
      dispatchCandidatePipelineEvent()
    })

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 300))
    })
    expect(result.current.applications).toEqual([firstApplication])
    expect(result.current.error).toBeNull()
  })

  it('removes candidate pipeline listeners on unmount', async () => {
    const { result, unmount } = renderHook(() => useMyApplications())

    await waitFor(() => {
      expect(result.current.applications).toEqual([firstApplication])
    })

    unmount()
    act(() => {
      dispatchCandidatePipelineEvent()
    })

    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(mockedGetMyApplications).toHaveBeenCalledTimes(1)
  })
})
