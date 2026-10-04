import { describe, expect, it, vi, beforeEach } from 'vitest'
import axios from 'axios'

import { getMySubscription } from './subscriptions'

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  const mockInstance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  }
  return {
    __esModule: true,
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => mockInstance),
    },
  }
})

const mockAxiosInstance = axios.create as ReturnType<typeof vi.fn>
const instance = mockAxiosInstance.mock.results[0].value

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getMySubscription', () => {
  it('requests GET /api/v1/subscriptions/me and returns subscription on 200', async () => {
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
        is_active: true,
        features: ['1 công việc đăng'],
      },
    }
    instance.get.mockResolvedValue(subscription as any)

    const result = await getMySubscription()

    expect(instance.get).toHaveBeenCalledWith('/subscriptions/me')
    expect(result).toEqual(subscription)
  })

  it('returns null on 404', async () => {
    instance.get.mockRejectedValueOnce({
      response: { status: 404 },
    })

    const result = await getMySubscription()

    expect(instance.get).toHaveBeenCalledWith('/subscriptions/me')
    expect(result).toBeNull()
  })

  it('propagates non-404 errors', async () => {
    instance.get.mockRejectedValueOnce(new Error('Internal server error'))

    await expect(getMySubscription()).rejects.toThrow('Internal server error')

    expect(instance.get).toHaveBeenCalledWith('/subscriptions/me')
  })
})