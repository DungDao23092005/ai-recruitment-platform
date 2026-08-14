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
})