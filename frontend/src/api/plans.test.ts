import { describe, expect, it, vi, beforeEach } from 'vitest'
import axios from 'axios'

import { getPlans, getPlan } from './plans'

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

describe('getPlans', () => {
  it('requests GET /api/v1/plans and returns RecruitmentPlan[]', async () => {
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
        features: ['1 công việc đăng', 'Xem hồ sơ ứng viên'],
      },
      {
        id: 'plan-2',
        name: 'Gói Nâng cao',
        description: 'Gói đăng tin nâng cao',
        price: 10000000,
        currency: 'VND',
        duration_days: 30,
        max_job_posts: 20,
        is_active: true,
        features: ['5 công việc đăng', 'Tiếp cận người dùng kích cỡ'],
      },
    ]
    instance.get.mockResolvedValue(plans as any)

    const result = await getPlans()

    expect(instance.get).toHaveBeenCalledWith('/plans')
    expect(result).toEqual(plans)
  })

  it('propagates API error', async () => {
    const message = 'Failed to load plans'
    instance.get.mockRejectedValueOnce(new Error(message))

    await expect(getPlans()).rejects.toEqual(new Error(message))

    expect(instance.get).toHaveBeenCalledWith('/plans')
  })
})

describe('getPlan', () => {
  it('requests GET /api/v1/plans/:planId and returns RecruitmentPlan', async () => {
    const plan = {
      id: 'plan-1',
      name: 'Gói Standard',
      description: 'Gói đăng tin cơ bản',
      price: 5000000,
      currency: 'VND',
      duration_days: 30,
      max_job_posts: 5,
      is_active: true,
      features: ['1 công việc đăng', 'Xem hồ sơ ứng viên'],
    }
    instance.get.mockResolvedValue(plan as any)

    const result = await getPlan('plan-1')

    expect(instance.get).toHaveBeenCalledWith('/plans/plan-1')
    expect(result).toEqual(plan)
  })

  it('propagates API error for invalid plan', async () => {
    const message = 'Plan not found'
    instance.get.mockRejectedValueOnce(new Error(message))

    await expect(getPlan('non-existent-id')).rejects.toEqual(new Error(message))

    expect(instance.get).toHaveBeenCalledWith('/plans/non-existent-id')
  })

  it('propagates API error for inactive plan', async () => {
    const message = 'Plan is inactive'
    instance.get.mockRejectedValueOnce(new Error(message))

    await expect(getPlan('inactive-plan-id')).rejects.toEqual(new Error(message))

    expect(instance.get).toHaveBeenCalledWith('/plans/inactive-plan-id')
  })
})