import { describe, expect, it, vi, beforeEach } from 'vitest'
import axios from 'axios'

import { getJobById, getMyJobById } from './jobs'

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  const mockInstance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
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

describe('getMyJobById', () => {
  it('requests /jobs/mine/{id}', async () => {
const job = { id: 'job-1', title: 'Backend Engineer' }
    instance.get.mockResolvedValue(job)

    const result = await getMyJobById('job-1')

    expect(instance.get).toHaveBeenCalledWith('/jobs/mine/job-1')
    expect(result).toEqual(job)
  })
})

describe('getJobById', () => {
  it('requests /jobs/{id}', async () => {
const job = { id: 'job-1', title: 'Backend Engineer' }
    instance.get.mockResolvedValue(job)

    const result = await getJobById('job-1')

    expect(instance.get).toHaveBeenCalledWith('/jobs/job-1')
    expect(result).toEqual(job)
  })
})
