import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  clearToken,
  getStoredToken,
  LOGOUT_EVENT,
  storeToken,
  TOKEN_STORAGE_KEY,
} from '@/api/client'
import { getCurrentUser, login as loginApi, logout as logoutApi } from '@/api/auth'
import type { LoginCredentials, User } from '@/types/auth'

interface AuthContextValue {
  currentUser: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (credentials: LoginCredentials) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)

  const applyLogout = useCallback(() => {
    clearToken()
    setCurrentUser(null)
    setToken(null)
  }, [])

  const logout = useCallback(async () => {
    try {
      // Attempt server-side token revocation
      await logoutApi()
    } catch (error) {
      // Even if backend fails, we still clear local state
      console.warn('Backend logout failed, clearing local state anyway:', error)
    } finally {
      // Always clear local auth state regardless of backend success/failure
      applyLogout()
      window.dispatchEvent(new CustomEvent(LOGOUT_EVENT))
    }
  }, [applyLogout])

  useEffect(() => {
    const storedToken = getStoredToken()
    if (!storedToken) {
      setIsLoading(false)
      return
    }

    let active = true
    setToken(storedToken)

    getCurrentUser()
      .then((user) => {
        if (active) {
          setCurrentUser(user)
        }
      })
      .catch(() => {
        if (active) {
          applyLogout()
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [applyLogout])

  useEffect(() => {
    const handleLogoutEvent = () => {
      applyLogout()
    }

    window.addEventListener(LOGOUT_EVENT, handleLogoutEvent)
    return () => {
      window.removeEventListener(LOGOUT_EVENT, handleLogoutEvent)
    }
  }, [applyLogout])

  // Cross-tab logout synchronization via storage event
  useEffect(() => {
    const handleStorageEvent = (event: StorageEvent) => {
      // Only react to changes in the auth token key
      if (event.key !== TOKEN_STORAGE_KEY) {
        return
      }

      // Only handle token removal (logout), not token addition (login)
      // Login is handled by the existing startup flow
      if (event.newValue === null && event.oldValue !== null) {
        // Token was removed in another tab - apply logout
        applyLogout()
      }
    }

    window.addEventListener('storage', handleStorageEvent)
    return () => {
      window.removeEventListener('storage', handleStorageEvent)
    }
  }, [applyLogout])

  const login = useCallback(
    async (credentials: LoginCredentials): Promise<User> => {
      const { access_token } = await loginApi(credentials)
      storeToken(access_token)
      setToken(access_token)

      const user = await getCurrentUser()
      setCurrentUser(user)
      return user
    },
    [],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      currentUser,
      token,
      isAuthenticated: currentUser !== null,
      isLoading,
      login,
      logout,
    }),
    [currentUser, token, isLoading, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}