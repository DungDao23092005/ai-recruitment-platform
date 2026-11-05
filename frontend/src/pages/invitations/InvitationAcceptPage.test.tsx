import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { InvitationAcceptPage } from './InvitationAcceptPage'
import type { InvitationPreview, Workspace } from '@/types/workspace'

const apiMocks = vi.hoisted(() => ({
  previewInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
}))

const authState = vi.hoisted(() => ({
  isAuthenticated: true,
  isLoading: false,
}))

const workspaceMocks = vi.hoisted(() => ({
  refreshWorkspaces: vi.fn().mockResolvedValue(undefined),
  selectWorkspace: vi.fn(),
}))

vi.mock('@/api/workspaces', () => apiMocks)
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => authState,
}))
vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: () => workspaceMocks,
}))

const preview: InvitationPreview = {
  company_name: 'TechNova AI',
  company_slug: 'technova-ai',
  email_masked: 'a***@example.com',
  role: 'recruiter',
  status: 'pending',
  expires_at: '2026-12-01T00:00:00Z',
  can_accept: true,
}

const workspace: Workspace = {
  company_id: 'company-1',
  company_name: 'TechNova AI',
  company_slug: 'technova-ai',
  membership_id: 'membership-1',
  role: 'recruiter',
  is_platform_admin: false,
}

function LoginProbe() {
  const location = useLocation()
  return <div data-testid="login-state">{JSON.stringify(location.state)}</div>
}

function renderPage(
  initialEntries: Parameters<typeof MemoryRouter>[0]['initialEntries'] = [
    '/invitations/accept',
  ],
) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/invitations/accept" element={<InvitationAcceptPage />} />
        <Route path="/login" element={<LoginProbe />} />
        <Route path="/recruiter/portal" element={<div>Recruiter portal</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  window.history.replaceState(null, '', '/')
  authState.isAuthenticated = true
  authState.isLoading = false
  apiMocks.previewInvitation.mockResolvedValue(preview)
  apiMocks.acceptInvitation.mockResolvedValue({
    workspace,
    membership_id: 'membership-1',
  })
})

describe('InvitationAcceptPage', () => {
  it('removes the fragment before rendering the invitation', async () => {
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token',
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })

    expect(window.location.hash).toBe('')
    expect(apiMocks.previewInvitation).toHaveBeenCalledWith('secret-token')
    expect(
      sessionStorage.getItem('ai_recruitment_pending_invite_token'),
    ).toBeNull()
  })

  it('submits the fragment token in the accept request body', async () => {
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token',
    )

    renderPage()

    fireEvent.click(
      await screen.findByRole('button', { name: 'Tham gia công ty' }),
    )

    await waitFor(() => {
      expect(apiMocks.acceptInvitation).toHaveBeenCalledWith('secret-token')
      expect(screen.getByText('Recruiter portal')).toBeInTheDocument()
    })
    expect(workspaceMocks.selectWorkspace).toHaveBeenCalledWith('company-1')
    expect(workspaceMocks.refreshWorkspaces).toHaveBeenCalled()
  })

  it('uses the in-memory router token after login without reading storage', async () => {
    renderPage([
      {
        pathname: '/invitations/accept',
        state: { invitationToken: 'state-token' },
      },
    ])

    await waitFor(() => {
      expect(apiMocks.previewInvitation).toHaveBeenCalledWith('state-token')
    })
    expect(sessionStorage.length).toBe(0)
  })

  it('carries the invitation token to login in router state', async () => {
    authState.isAuthenticated = false
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token',
    )

    renderPage()

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Đăng nhập để tham gia',
      }),
    )

    await waitFor(() => {
      expect(screen.getByTestId('login-state')).toHaveTextContent(
        '"invitationToken":"secret-token"',
      )
    })
    expect(screen.getByTestId('login-state')).toHaveTextContent(
      '"from":"/invitations/accept"',
    )
    expect(window.location.hash).toBe('')
    expect(sessionStorage.length).toBe(0)
  })

  it('shows a safe error for an invalid invitation link', async () => {
    const error = new Error('not found')
    Object.assign(error, {
      response: {
        status: 404,
        data: { detail: 'Invitation not found' },
      },
    })
    apiMocks.previewInvitation.mockRejectedValue(error)
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=bad-token',
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Invitation not found',
      )
    })
    expect(window.location.hash).toBe('')
    expect(screen.queryByText('bad-token')).not.toBeInTheDocument()
  })
})
