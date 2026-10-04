import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useMySubscription } from '@/features/subscriptions/hooks/useMySubscription'

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