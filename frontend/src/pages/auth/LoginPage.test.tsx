import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { LoginPage } from './LoginPage'
import { AuthProvider } from '@/contexts/AuthContext'
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

function InvitationProbe() {
  const location = useLocation()
  return <div data-testid="invitation-state">{JSON.stringify(location.state)}</div>
}

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/candidate/portal" element={<div>Candidate Portal Page</div>} />
          <Route path="/invitations/accept" element={<InvitationProbe />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('LoginPage', () => {
  it('shows validation errors for empty form', async () => {
    renderLoginPage()

    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }))

    await waitFor(() => {
      expect(screen.getByText('Email không được để trống')).toBeInTheDocument()
      expect(
        screen.getByText('Mật khẩu không được để trống'),
      ).toBeInTheDocument()
    })
    expect(mockedLogin).not.toHaveBeenCalled()
  })

  it('calls login API with credentials', async () => {
    mockedLogin.mockResolvedValue({
      access_token: 'token-abc',
      token_type: 'bearer',
    })
    mockedGetCurrentUser.mockResolvedValue(mockUser)

    renderLoginPage()

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'candidate@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Mật khẩu'), {
      target: { value: 'password1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }))

    await waitFor(() => {
      expect(mockedLogin).toHaveBeenCalledWith({
        email: 'candidate@example.com',
        password: 'password1',
      })
    })
  })

  it('shows error message on wrong password', async () => {
    const error = new Error('401')
    Object.assign(error, { response: { status: 401 } })
    mockedLogin.mockRejectedValue(error)

    renderLoginPage()

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'candidate@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Mật khẩu'), {
      target: { value: 'wrongpass' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }))

    await waitFor(() => {
      expect(
        screen.getByText('Email hoặc mật khẩu không chính xác.'),
      ).toBeInTheDocument()
    })
  })

  it('disables submit button while loading', async () => {
    let resolveLogin!: (value: { access_token: string; token_type: string }) => void
    mockedLogin.mockReturnValue(
      new Promise((resolve) => {
        resolveLogin = resolve
      }),
    )
    mockedGetCurrentUser.mockResolvedValue(mockUser)

    renderLoginPage()

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'candidate@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Mật khẩu'), {
      target: { value: 'password1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }))

    const button = screen.getByRole('button', { name: /Đang tải/i })
    expect(button).toBeDisabled()

    resolveLogin({ access_token: 'token-abc', token_type: 'bearer' })
  })

  it('navigates to candidate profile on successful login', async () => {
    mockedLogin.mockResolvedValue({
      access_token: 'token-abc',
      token_type: 'bearer',
    })
    mockedGetCurrentUser.mockResolvedValue(mockUser)

    renderLoginPage()

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'candidate@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Mật khẩu'), {
      target: { value: 'password1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }))

    await waitFor(() => {
      expect(
        screen.getByText('Candidate Portal Page'),
      ).toBeInTheDocument()
    })
  })

  it('returns to the invitation with the token in router state', async () => {
    mockedLogin.mockResolvedValue({
      access_token: 'token-abc',
      token_type: 'bearer',
    })
    mockedGetCurrentUser.mockResolvedValue(mockUser)

    const { container } = render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/login',
            state: {
              from: '/invitations/accept',
              invitationToken: 'invite-token',
            },
          },
        ]}
      >
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/invitations/accept" element={<InvitationProbe />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'candidate@example.com' },
    })
    fireEvent.change(container.querySelector('input[name="password"]')!, {
      target: { value: 'password1' },
    })
    fireEvent.click(container.querySelector('button[type="submit"]')!)

    await waitFor(() => {
      expect(screen.getByTestId('invitation-state')).toHaveTextContent(
        '"invitationToken":"invite-token"',
      )
    })
  })
})