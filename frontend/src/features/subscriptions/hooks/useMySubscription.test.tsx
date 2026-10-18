import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useMySubscription } from '@/features/subscriptions/hooks/useMySubscription'
import type { Subscription } from '@/types/subscription'

// Mock the API module
vi.mock('@/api/subscriptions', async () => {
  const actual = await import('@/api/subscriptions')
  return {
    ...actual,
    getMySubscription: vi.fn(),
  }
})

const mockedGetMySubscription = (await import('@/api/subscriptions')).getMySubscription

describe('useMySubscription', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns subscription on 200', async () => {
    const subscription = {
      id: 'sub-1',
      user_id: 'user-1',
      plan_id: 'plan-1',
      status: 'active' as const,
      start_date: '2024-01-01',
      end_date: '2025-01-01',
      plan: {
        id: 'plan-1',
        name: 'Gói Standard',
        description: 'Gói đăng tin cơ bản',
        price: 5000000,
        currency: 'VND',
        duration_days: 30,
        max_job_posts: 5,
        features: ['1 công việc đăng'],
      },
    }
    mockedGetMySubscription.mockResolvedValueOnce(subscription as any)

    const { result } = renderHook(() => useMySubscription())

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isLoading).toBe(false)
    expect(result.current.subscription).toEqual(subscription)
    expect(result.current.error).toBeNull()
  })

  it('returns null on 404', async () => {
    mockedGetMySubscription.mockRejectedValueOnce({
      response: { status: 404 },
    })

    const { result } = renderHook(() => useMySubscription())

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isLoading).toBe(false)
    expect(result.current.subscription).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('sets error on non-404 error', async () => {
    mockedGetMySubscription.mockRejectedValueOnce({
      response: { status: 500, message: 'Internal server error' },
    })

    const { result } = renderHook(() => useMySubscription())

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isLoading).toBe(false)
    expect(result.current.subscription).toBeNull()
    expect(result.current.error).toEqual('Internal server error')
  })

  it('starts with loading state', () => {
    mockedGetMySubscription.mockResolvedValueOnce(null as any)

    const { result } = renderHook(() => useMySubscription())

    expect(result.current.isLoading).toBe(true)
    expect(result.current.subscription).toBeNull()
    expect(result.current.error).toBeNull()
  })
})

const activeSubscription: Subscription = {
  id: 'sub-1',
  user_id: 'user-1',
  plan_id: 'plan-1',
  status: 'active',
  started_at: '2024-01-01',
  expires_at: '2099-01-01',
  plan: {
    id: 'plan-1',
    name: 'Gói Standard',
    description: 'Gói đăng tin cơ bản',
    price: 5000000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 5,
    max_candidate_searches: 10,
    max_ai_features: 3,
    is_active: true,
    features: ['1 công việc đăng'],
  },
}

const realtimeWaitOptions = { timeout: 2000 }

describe('useMySubscription realtime invalidation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('silently refreshes when a subscription:changed event arrives', async () => {
    mockedGetMySubscription
      .mockResolvedValueOnce(activeSubscription as any)
      .mockResolvedValueOnce(null)

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.subscription).toEqual(activeSubscription)

    act(() => {
      window.dispatchEvent(
        new CustomEvent('subscription:changed', {
          detail: { notification_type: 'subscription_revoked', entity_type: 'subscription' },
        }),
      )
    })

    await waitFor(
      () => expect(mockedGetMySubscription).toHaveBeenCalledTimes(2),
      realtimeWaitOptions,
    )
    await waitFor(() => expect(result.current.subscription).toBeNull())
    expect(result.current.error).toBeNull()
  })

  it('does not toggle isLoading while a silent refresh is in flight', async () => {
    let resolveSilent!: (value: Subscription | null) => void
    const silentPromise = new Promise<Subscription | null>((resolve) => {
      resolveSilent = resolve
    })
    mockedGetMySubscription
      .mockResolvedValueOnce(activeSubscription as any)
      .mockReturnValueOnce(silentPromise)

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      window.dispatchEvent(new CustomEvent('subscription:changed'))
    })

    await waitFor(
      () => expect(mockedGetMySubscription).toHaveBeenCalledTimes(2),
      realtimeWaitOptions,
    )
    expect(result.current.isLoading).toBe(false)

    act(() => {
      resolveSilent(null)
    })
    await waitFor(() => expect(result.current.subscription).toBeNull())
    expect(result.current.isLoading).toBe(false)
  })

  it('keeps the last known state when a silent refresh fails', async () => {
    mockedGetMySubscription
      .mockResolvedValueOnce(activeSubscription as any)
      .mockRejectedValueOnce(new Error('network down'))

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      window.dispatchEvent(new CustomEvent('subscription:changed'))
    })

    await waitFor(
      () => expect(mockedGetMySubscription).toHaveBeenCalledTimes(2),
      realtimeWaitOptions,
    )
    expect(result.current.subscription).toEqual(activeSubscription)
    expect(result.current.error).toBeNull()
    expect(result.current.isLoading).toBe(false)
  })

  it('coalesces rapid invalidations into a single silent refresh', async () => {
    mockedGetMySubscription.mockResolvedValue(activeSubscription as any)

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(mockedGetMySubscription).toHaveBeenCalledTimes(1)

    act(() => {
      window.dispatchEvent(new CustomEvent('subscription:changed'))
      window.dispatchEvent(
        new CustomEvent('admin:subscription:changed', {
          detail: { user_id: activeSubscription.user_id },
        }),
      )
      window.dispatchEvent(new CustomEvent('stream:connected'))
    })

    await waitFor(
      () => expect(mockedGetMySubscription).toHaveBeenCalledTimes(2),
      realtimeWaitOptions,
    )
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(mockedGetMySubscription).toHaveBeenCalledTimes(2)
  })

  it('ignores an admin invalidation that targets a different user', async () => {
    mockedGetMySubscription.mockResolvedValue(activeSubscription as any)

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      window.dispatchEvent(
        new CustomEvent('admin:subscription:changed', {
          detail: { user_id: 'someone-else' },
        }),
      )
    })

    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(mockedGetMySubscription).toHaveBeenCalledTimes(1)
  })

  it('refreshes when an admin invalidation targets the current user', async () => {
    mockedGetMySubscription.mockResolvedValue(activeSubscription as any)

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      window.dispatchEvent(
        new CustomEvent('admin:subscription:changed', {
          detail: { user_id: activeSubscription.user_id },
        }),
      )
    })

    await waitFor(
      () => expect(mockedGetMySubscription).toHaveBeenCalledTimes(2),
      realtimeWaitOptions,
    )
  })

  it('refreshes when the notification stream reconnects', async () => {
    mockedGetMySubscription.mockResolvedValue(activeSubscription as any)

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      window.dispatchEvent(new CustomEvent('stream:connected'))
    })

    await waitFor(
      () => expect(mockedGetMySubscription).toHaveBeenCalledTimes(2),
      realtimeWaitOptions,
    )
  })

  it('refreshes when the document becomes visible again', async () => {
    mockedGetMySubscription.mockResolvedValue(activeSubscription as any)
    const visibilitySpy = vi
      .spyOn(document, 'visibilityState', 'get')
      .mockReturnValue('visible')

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    await waitFor(
      () => expect(mockedGetMySubscription).toHaveBeenCalledTimes(2),
      realtimeWaitOptions,
    )

    visibilitySpy.mockRestore()
  })

  it('ignores a stale response that resolves after a newer request', async () => {
    const staleSubscription = { ...activeSubscription, id: 'sub-stale' }
    const freshSubscription = { ...activeSubscription, id: 'sub-fresh' }

    let resolveStale!: (value: Subscription | null) => void
    const stalePromise = new Promise<Subscription | null>((resolve) => {
      resolveStale = resolve
    })
    mockedGetMySubscription
      .mockReturnValueOnce(stalePromise)
      .mockResolvedValueOnce(freshSubscription as any)

    const { result } = renderHook(() => useMySubscription())
    await waitFor(() => expect(mockedGetMySubscription).toHaveBeenCalledTimes(1))

    act(() => {
      result.current.refetch()
    })
    await waitFor(() => expect(mockedGetMySubscription).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(result.current.subscription?.id).toBe('sub-fresh'))

    act(() => {
      resolveStale(staleSubscription)
    })
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(result.current.subscription?.id).toBe('sub-fresh')
    expect(result.current.isLoading).toBe(false)
  })

  it('does not update state after unmount', async () => {
    let resolveFetch!: (value: Subscription | null) => void
    const pending = new Promise<Subscription | null>((resolve) => {
      resolveFetch = resolve
    })
    mockedGetMySubscription.mockReturnValueOnce(pending)

    const { unmount } = renderHook(() => useMySubscription())
    await waitFor(() => expect(mockedGetMySubscription).toHaveBeenCalledTimes(1))

    unmount()

    await act(async () => {
      resolveFetch(activeSubscription)
      await Promise.resolve()
    })
    expect(mockedGetMySubscription).toHaveBeenCalledTimes(1)
  })
})