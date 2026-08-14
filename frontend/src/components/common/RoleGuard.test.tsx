import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { RoleGuard } from './RoleGuard'
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

const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)

function renderRoleGuard(role: 'candidate' | 'recruiter', allowedRoles: Array<'candidate' | 'recruiter'>) {
  const user: User = { ...mockUser, role }
  mockedGetCurrentUser.mockResolvedValue(user)
  localStorage.setItem('ai_recruitment_token', 'token-abc')

  return render(
    <MemoryRouter initialEntries={['/guarded']}>
      <AuthProvider>
        <Routes>
          <Route
            path="/guarded"
            element={
              <RoleGuard allowedRoles={allowedRoles}>
                <div>Protected Content</div>
              </RoleGuard>
            }
          />
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/" element={<div>Home Page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('RoleGuard', () => {
  it('renders children when role is allowed', async () => {
    renderRoleGuard('candidate', ['candidate'])

    await waitFor(() => {
      expect(screen.getByText('Protected Content')).toBeInTheDocument()
    })
    expect(screen.queryByText('Home Page')).not.toBeInTheDocument()
  })

  it('redirects away when role is not allowed', async () => {
    renderRoleGuard('candidate', ['recruiter'])

    await waitFor(() => {
      expect(screen.getByText('Home Page')).toBeInTheDocument()
    })
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('redirects to login when unauthenticated', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('401'))
    localStorage.removeItem('ai_recruitment_token')

    render(
      <MemoryRouter initialEntries={['/guarded']}>
        <AuthProvider>
          <Routes>
            <Route
              path="/guarded"
              element={
                <RoleGuard allowedRoles={['candidate']}>
                  <div>Protected Content</div>
                </RoleGuard>
              }
            />
            <Route path="/login" element={<div>Login Page</div>} />
            <Route path="/" element={<div>Home Page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Login Page')).toBeInTheDocument()
    })
  })
})