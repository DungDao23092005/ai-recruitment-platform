import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act } from 'react'

import { AuthProvider, useAuth } from './AuthContext'
import { LOGOUT_EVENT, TOKEN_STORAGE_KEY } from '@/api/client'
import * as authApi from '@/api/auth'
import type { User } from '@/types/auth'

const mockUser: User = {
  id: 'user-1',
  email: 'candidate@example.com',
  role: 'candidate',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  getCurrentUser: vi.fn(),
  register: vi.fn(),
  createCandidateProfile: vi.fn(),
  createRecruiterProfile: vi.fn(),
}))

const mockedLogin = vi.mocked(authApi.login)
const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)

function TestConsumer() {
  const { currentUser, isAuthenticated, isLoading, login, logout } = useAuth()

  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="user">{currentUser?.email ?? 'none'}</span>
      <button type="button" onClick={() => login({ email: 'a@b.c', password: 'password1' })}>
        Login
      </button>
      <button type="button" onClick={logout}>
        Logout
      </button>
    </div>
  )
}

function renderProvider() {
  return render(
    <AuthProvider>
      <TestConsumer />
    </AuthProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('AuthContext', () => {
  it('starts unauthenticated when no token is stored', async () => {
    renderProvider()

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    })
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
    expect(screen.getByTestId('user')).toHaveTextContent('none')
  })

  it('logs in successfully, stores token and loads current user', async () => {
    mockedLogin.mockResolvedValue({
      access_token: 'token-123',
      token_type: 'bearer',
    })
    mockedGetCurrentUser.mockResolvedValue(mockUser)

    renderProvider()
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false'),
    )

    await act(async () => {
      screen.getByRole('button', { name: 'Login' }).click()
    })

    expect(mockedLogin).toHaveBeenCalledWith({
      email: 'a@b.c',
      password: 'password1',
    })
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('token-123')
    expect(screen.getByTestId('authenticated')).toHaveTextContent('true')
    expect(screen.getByTestId('user')).toHaveTextContent('candidate@example.com')
  })

  it('loads token and current user on startup when token exists', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'stored-token')
    mockedGetCurrentUser.mockResolvedValue(mockUser)

    renderProvider()

    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('candidate@example.com'),
    )
    expect(screen.getByTestId('authenticated')).toHaveTextContent('true')
    expect(screen.getByTestId('loading')).toHaveTextContent('false')
  })

  it('clears auth state when stored token is invalid', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'bad-token')
    mockedGetCurrentUser.mockRejectedValue(new Error('401'))

    renderProvider()

    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false'),
    )
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull()
  })

  it('logs out and clears token and user', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'stored-token')
    mockedGetCurrentUser.mockResolvedValue(mockUser)

    renderProvider()
    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('candidate@example.com'),
    )

    act(() => {
      screen.getByRole('button', { name: 'Logout' }).click()
    })

    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull()
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
    expect(screen.getByTestId('user')).toHaveTextContent('none')
  })

  it('resets auth state when logout event is dispatched', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'stored-token')
    mockedGetCurrentUser.mockResolvedValue(mockUser)

    renderProvider()
    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('candidate@example.com'),
    )

    act(() => {
      window.dispatchEvent(new CustomEvent(LOGOUT_EVENT))
    })

    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull()
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
  })

  describe('cross-tab logout synchronization via storage event', () => {
    it('does not clear auth state for unrelated storage key changes', async () => {
      localStorage.setItem(TOKEN_STORAGE_KEY, 'stored-token')
      mockedGetCurrentUser.mockResolvedValue(mockUser)

      renderProvider()
      await waitFor(() =>
        expect(screen.getByTestId('user')).toHaveTextContent('candidate@example.com'),
      )

      // Simulate storage event for unrelated key
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: 'some_other_key',
            oldValue: 'old',
            newValue: 'new',
            storageArea: localStorage,
          })
        )
      })

      // Auth state should remain unchanged
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true')
      expect(screen.getByTestId('user')).toHaveTextContent('candidate@example.com')
    })

    it('clears auth state when token is removed in another tab', async () => {
      localStorage.setItem(TOKEN_STORAGE_KEY, 'stored-token')
      mockedGetCurrentUser.mockResolvedValue(mockUser)

      renderProvider()
      await waitFor(() =>
        expect(screen.getByTestId('user')).toHaveTextContent('candidate@example.com'),
      )

      // Simulate storage event for token removal in another tab
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: TOKEN_STORAGE_KEY,
            oldValue: 'stored-token',
            newValue: null,
            storageArea: localStorage,
          })
        )
      })

      // Auth state should be cleared
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
      expect(screen.getByTestId('user')).toHaveTextContent('none')
      expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull()
    })

    it('does not log out when token is added in another tab', async () => {
      mockedGetCurrentUser.mockResolvedValue(mockUser)

      renderProvider()
      await waitFor(() =>
        expect(screen.getByTestId('loading')).toHaveTextContent('false'),
      )
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false')

      // Simulate storage event for token addition in another tab
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: TOKEN_STORAGE_KEY,
            oldValue: null,
            newValue: 'new-token-from-another-tab',
            storageArea: localStorage,
          })
        )
      })

      // Should not automatically log in - login is handled by startup flow
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
})
  })
})

  it('cleans up storage event listener on unmount', async () => {
    const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener')

    const { unmount } = renderProvider()
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false'),
    )

    unmount()

    // Should have removed the storage event listener
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      'storage',
      expect.any(Function)
    )
  })