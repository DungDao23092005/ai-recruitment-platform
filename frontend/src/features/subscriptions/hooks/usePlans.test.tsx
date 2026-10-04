import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { waitFor } from '@testing-library/react'
import { usePlans } from '@/features/subscriptions/hooks/usePlans'

// Mock the API module
vi.mock('@/api/plans', async () => {
  const actual = await import('@/api/plans')
  return {
    ...actual,
    getPlans: vi.fn(),
  }
})

const mockedGetPlans = (await import('@/api/plans')).getPlans

describe('usePlans', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts with loading state', () => {
    mockedGetPlans.mockResolvedValueOnce([] as any)

    const { result } = renderHook(() => usePlans())

    expect(result.current.isLoading).toBe(true)
    expect(result.current.plans).toEqual([])
    expect(result.current.error).toBeNull()
  })

  it('populates plans on success', async () => {
    const plans = [
      {
        id: 'plan-1',
        name: 'Gói Standard',
        description: 'Gói đăng tin cơ bản',
        price: 5000000,
        currency: 'VND',
        duration_days: 30,
        max_job_posts: 5,
        is_active: true,
        features: ['1 công việc đăng'],
      },
    ]
    mockedGetPlans.mockResolvedValueOnce(plans as any)

    const { result } = renderHook(() => usePlans())

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isLoading).toBe(false)
    expect(result.current.plans).toEqual(plans)
    expect(result.current.error).toBeNull()
  })

  it('sets error on API failure', async () => {
    const message = 'Failed to load plans'
    mockedGetPlans.mockRejectedValueOnce(new Error(message))

    const { result } = renderHook(() => usePlans())

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toEqual(message)
    expect(result.current.plans).toEqual([])
  })
})