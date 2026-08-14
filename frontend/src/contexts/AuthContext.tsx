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
} from '@/api/client'
import { getCurrentUser, login as loginApi } from '@/api/auth'
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

  const logout = useCallback(() => {
    applyLogout()
    window.dispatchEvent(new CustomEvent(LOGOUT_EVENT))
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