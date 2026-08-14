import { describe, expect, it, vi, beforeEach } from 'vitest'
import axios from 'axios'

import apiClient, {
  API_BASE_URL,
  TOKEN_STORAGE_KEY,
  LOGOUT_EVENT,
  getStoredToken,
  storeToken,
  clearToken,
} from './client'

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  const mockInstance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
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

type RequestFulfilled = (
  config: { headers: Record<string, string> },
) => { headers: Record<string, string> }

type ResponseFulfilled = (response: unknown) => unknown
type ResponseRejected = (error: { response?: { status: number } }) => unknown

function getHandlers() {
  const instance = mockAxiosInstance.mock.results[0].value
  const requestUse = instance.interceptors.request.use as ReturnType<
    typeof vi.fn
  >
  const responseUse = instance.interceptors.response.use as ReturnType<
    typeof vi.fn
  >
  return {
    requestFulfilled: requestUse.mock.calls[0][0] as RequestFulfilled,
    requestRejected: requestUse.mock.calls[0][1] as (e: unknown) => unknown,
    responseFulfilled: responseUse.mock.calls[0][0] as ResponseFulfilled,
    responseRejected: responseUse.mock.calls[0][1] as ResponseRejected,
  }
}

beforeEach(() => {
  localStorage.clear()
})

describe('apiClient', () => {
  it('creates axios with the default API base URL', () => {
    expect(mockAxiosInstance).toHaveBeenCalledWith(
      expect.objectContaining({ baseURL: API_BASE_URL }),
    )
    expect(API_BASE_URL).toBe('http://localhost:8000/api/v1')
  })

  it('exposes the default apiClient instance', () => {
    expect(apiClient).toBeDefined()
    expect(typeof apiClient.get).toBe('function')
  })

  it('stores and retrieves the token', () => {
    expect(getStoredToken()).toBeNull()
    storeToken('abc123')
    expect(getStoredToken()).toBe('abc123')
    clearToken()
    expect(getStoredToken()).toBeNull()
  })

  it('injects Bearer token when token exists', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'token-xyz')
    const { requestFulfilled } = getHandlers()

    const result = requestFulfilled({ headers: {} })

    expect(result.headers.Authorization).toBe('Bearer token-xyz')
  })

  it('does not add Authorization header without a token', () => {
    const { requestFulfilled } = getHandlers()

    const result = requestFulfilled({ headers: {} })

    expect(result.headers.Authorization).toBeUndefined()
  })

  it('returns response.data on success', () => {
    const { responseFulfilled } = getHandlers()

    const result = responseFulfilled({ data: { ok: true }, status: 200 })

    expect(result).toEqual({ ok: true })
  })

  it('clears token and dispatches logout event on 401', async () => {
    const { responseRejected } = getHandlers()

    localStorage.setItem(TOKEN_STORAGE_KEY, 'expired-token')
    const listener = vi.fn()
    window.addEventListener(LOGOUT_EVENT, listener)

    const error = { response: { status: 401 } }

    await expect(responseRejected(error)).rejects.toEqual(error)
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull()
    expect(listener).toHaveBeenCalled()
  })

  it('does not clear token on non-401 error', async () => {
    const { responseRejected } = getHandlers()

    localStorage.setItem(TOKEN_STORAGE_KEY, 'still-valid')

    const error = { response: { status: 500 } }

    await expect(responseRejected(error)).rejects.toEqual(error)
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('still-valid')
  })
})