import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'
import { formatLockNotice, storeLockNotice } from '@/utils/lockNotice'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export const TOKEN_STORAGE_KEY = 'ai_recruitment_token'

export const LOGOUT_EVENT = 'ai-recruitment:logout'

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function storeToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}

export function dispatchLogoutEvent(): void {
  window.dispatchEvent(new CustomEvent(LOGOUT_EVENT))
}

// Only the exact locked-account rejection triggers forced eviction; every other
// 403 (e.g. insufficient role) is left untouched.
function isInactiveUserError(error: AxiosError): boolean {
  const data = error.response?.data as { detail?: unknown } | undefined
  return data?.detail === 'Inactive user'
}

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getStoredToken()
    if (token) {
      config.headers = AxiosHeaders.from(config.headers)
      config.headers.set('Authorization', `Bearer ${token}`)
    }
    // If the request body is FormData, remove Content-Type header
    // so Axios can generate the correct multipart/form-data boundary
    if (config.data instanceof FormData) {
      config.headers.delete('Content-Type')
    }
    return config
  },
  (error: AxiosError) => Promise.reject(error),
)

apiClient.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError) => {
    const status = error.response?.status
    if (status === 401) {
      clearToken()
      dispatchLogoutEvent()
    } else if (status === 403 && isInactiveUserError(error)) {
      // The account was locked while a request was in flight. This is a fallback
      // for when the realtime stream is unavailable: store a one-time notice
      // (never clobbering a more specific SSE reason) and evict the session
      // through the same local mechanism as a 401. The backend `is_active`
      // guard stays the authoritative enforcement.
      storeLockNotice(formatLockNotice(null))
      clearToken()
      dispatchLogoutEvent()
    }
    return Promise.reject(error)
  },
)

export default apiClient