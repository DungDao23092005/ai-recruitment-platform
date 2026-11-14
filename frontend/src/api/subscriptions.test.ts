import { describe, expect, it, vi, beforeEach } from 'vitest'
import axios from 'axios'

import {
  getCompanySubscription,
  getCompanySubscriptionHistory,
  getCompanyUsages,
  getMySubscription,
} from './subscriptions'

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
describe('getCompanySubscription', () => {
  it('requests GET /api/v1/subscriptions/company and returns subscription', async () => {
    const subscription = { id: 'sub-company', company_id: 'company-1' }
    instance.get.mockResolvedValue(subscription as any)

    const result = await getCompanySubscription()

    expect(instance.get).toHaveBeenCalledWith('/subscriptions/company')
    expect(result).toEqual(subscription)
  })

  it('returns null on 404', async () => {
    instance.get.mockRejectedValueOnce({ response: { status: 404 } })

    await expect(getCompanySubscription()).resolves.toBeNull()
  })

  it('propagates 403 authorization errors', async () => {
    instance.get.mockRejectedValueOnce({ response: { status: 403 } })

    await expect(getCompanySubscription()).rejects.toEqual({
      response: { status: 403 },
    })
  })
})

describe('getCompanySubscriptionHistory', () => {
  it('requests GET /api/v1/subscriptions/company/history', async () => {
    const orders = [{ id: 'order-1' }]
    instance.get.mockResolvedValue(orders as any)

    const result = await getCompanySubscriptionHistory()

    expect(instance.get).toHaveBeenCalledWith('/subscriptions/company/history')
    expect(result).toEqual(orders)
  })
})

describe('getCompanyUsages', () => {
  it('requests GET /api/v1/subscriptions/company/usages without empty params', async () => {
    const response = {
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      total_pages: 0,
    }
    instance.get.mockResolvedValue(response as any)

    const result = await getCompanyUsages()

    expect(instance.get).toHaveBeenCalledWith(
      '/subscriptions/company/usages',
      { params: {} },
    )
    expect(result).toEqual(response)
  })

  it('forwards page, dates, feature and member filters', async () => {
    instance.get.mockResolvedValue({ items: [] } as any)

    await getCompanyUsages({
      page: 2,
      page_size: 20,
      start_date: '2026-11-01',
      end_date: '2026-11-14',
      feature_type: 'job_post',
      user_id: 'user-1',
    })

    expect(instance.get).toHaveBeenCalledWith(
      '/subscriptions/company/usages',
      {
        params: {
          page: 2,
          page_size: 20,
          start_date: '2026-11-01',
          end_date: '2026-11-14',
          feature_type: 'job_post',
          user_id: 'user-1',
        },
      },
    )
  })
})
