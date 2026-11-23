import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { InvitationAcceptPage } from './InvitationAcceptPage'
import type { InvitationPreview, MyInvitation, Workspace } from '@/types/workspace'

const apiMocks = vi.hoisted(() => ({
  previewInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
  declineInvitation: vi.fn(),
  getMyInvitations: vi.fn(),
  acceptMyInvitation: vi.fn(),
  declineMyInvitation: vi.fn(),
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

const myInvitation: MyInvitation = {
  id: 'invitation-in-app-1',
  company_id: 'company-1',
  company_name: 'TechNova AI',
  company_slug: 'technova-ai',
  role: 'recruiter',
  status: 'pending',
  expires_at: '2026-12-01T00:00:00Z',
  created_at: '2026-11-20T00:00:00Z',
  can_accept: true,
}

function LoginProbe() {
  const location = useLocation()
  return <div data-testid="login-state">{JSON.stringify(location.state)}</div>
}

function RegisterProbe() {
  const location = useLocation()
  return <div data-testid="register-state">{JSON.stringify(location.state)}</div>
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
        <Route path="/register" element={<RegisterProbe />} />
        <Route path="/recruiter/portal" element={<div>Recruiter portal</div>} />
        <Route path="/" element={<div>Home page</div>} />
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
  apiMocks.declineInvitation.mockResolvedValue({
    invitation_id: 'invitation-1',
    status: 'declined',
  })
  apiMocks.getMyInvitations.mockResolvedValue([myInvitation])
  apiMocks.acceptMyInvitation.mockResolvedValue({
    workspace,
    membership_id: 'membership-1',
  })
  apiMocks.declineMyInvitation.mockResolvedValue({
    invitation_id: 'invitation-in-app-1',
    status: 'declined',
  })
})

describe('InvitationAcceptPage', () => {
  it('removes the fragment before rendering the invitation while preserving state', async () => {
    window.history.replaceState(
      { existingMeta: 'preserved' },
      '',
      '/invitations/accept#token=secret-token&action=accept',
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })

    expect(window.location.hash).toBe('')
    expect(window.history.state).toEqual({ existingMeta: 'preserved' })
    expect(apiMocks.previewInvitation).toHaveBeenCalledWith('secret-token')
  })

  it('submits the fragment token in the accept request body after explicit confirmation', async () => {
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token&action=accept',
    )

    renderPage()

    fireEvent.click(
      await screen.findByRole('button', { name: 'Chấp nhận lời mời' }),
    )

    // Verify confirmation modal opens
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(
      screen.getByText('Xác nhận chấp nhận lời mời'),
    ).toBeInTheDocument()

    // Confirm acceptance
    fireEvent.click(
      screen.getByRole('button', { name: 'Xác nhận tham gia' }),
    )

    await waitFor(() => {
      expect(apiMocks.acceptInvitation).toHaveBeenCalledWith('secret-token')
      expect(screen.getByText('Recruiter portal')).toBeInTheDocument()
    })
    expect(workspaceMocks.selectWorkspace).toHaveBeenCalledWith('company-1')
    expect(workspaceMocks.refreshWorkspaces).toHaveBeenCalled()
  })

  it('declines the invitation via fragment token after explicit confirmation', async () => {
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token&action=decline',
    )

    renderPage()

    fireEvent.click(
      await screen.findByRole('button', { name: 'Từ chối lời mời' }),
    )

    // Verify confirmation modal opens for decline
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(
      screen.getByText('Xác nhận từ chối lời mời'),
    ).toBeInTheDocument()

    // Confirm decline
    fireEvent.click(
      screen.getByRole('button', { name: 'Xác nhận từ chối' }),
    )

    await waitFor(() => {
      expect(apiMocks.declineInvitation).toHaveBeenCalledWith('secret-token')
      expect(screen.getByText('Đã từ chối lời mời')).toBeInTheDocument()
    })
  })

  it('allows cancelling the confirmation dialog without mutating state', async () => {
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token&action=accept',
    )

    renderPage()

    fireEvent.click(
      await screen.findByRole('button', { name: 'Chấp nhận lời mời' }),
    )

    expect(screen.getByRole('dialog')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(apiMocks.acceptInvitation).not.toHaveBeenCalled()
    expect(apiMocks.declineInvitation).not.toHaveBeenCalled()
  })

  it('allows switching intent from decline to accept', async () => {
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token&action=decline',
    )

    renderPage()

    // Landed with decline action intent, but user chooses accept
    fireEvent.click(
      await screen.findByRole('button', { name: 'Chấp nhận lời mời' }),
    )

    expect(screen.getByText('Xác nhận chấp nhận lời mời')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận tham gia' }))

    await waitFor(() => {
      expect(apiMocks.acceptInvitation).toHaveBeenCalledWith('secret-token')
      expect(screen.getByText('Recruiter portal')).toBeInTheDocument()
    })
  })

  it('supports in-app flow via getMyInvitations without token in URL', async () => {
    renderPage(['/invitations/accept'])

    await waitFor(() => {
      expect(apiMocks.getMyInvitations).toHaveBeenCalled()
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Chấp nhận lời mời' }))
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận tham gia' }))

    await waitFor(() => {
      expect(apiMocks.acceptMyInvitation).toHaveBeenCalledWith(
        'invitation-in-app-1',
      )
    })
  })

  it('supports in-app flow declining without token in URL', async () => {
    renderPage(['/invitations/accept'])

    await waitFor(() => {
      expect(apiMocks.getMyInvitations).toHaveBeenCalled()
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Từ chối lời mời' }))
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận từ chối' }))

    await waitFor(() => {
      expect(apiMocks.declineMyInvitation).toHaveBeenCalledWith(
        'invitation-in-app-1',
      )
      expect(screen.getByText('Đã từ chối lời mời')).toBeInTheDocument()
    })
  })

  it('uses in-memory router token after login without reading storage', async () => {
    renderPage([
      {
        pathname: '/invitations/accept',
        state: { invitationToken: 'state-token', invitationAction: 'accept' },
      },
    ])

    await waitFor(() => {
      expect(apiMocks.previewInvitation).toHaveBeenCalledWith('state-token')
    })
    expect(sessionStorage.length).toBe(0)
  })

  it('carries invitation token and action to login and register in router state', async () => {
    authState.isAuthenticated = false
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token&action=decline',
    )

    renderPage()

    // Login navigation carries state
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Đăng nhập để tham gia',
      }),
    )

    await waitFor(() => {
      expect(screen.getByTestId('login-state')).toHaveTextContent(
        '"invitationToken":"secret-token"',
      )
      expect(screen.getByTestId('login-state')).toHaveTextContent(
        '"invitationAction":"decline"',
      )
    })
  })

  it('carries invitation token and action to register in router state', async () => {
    authState.isAuthenticated = false
    window.history.replaceState(
      null,
      '',
      '/invitations/accept#token=secret-token&action=accept',
    )

    renderPage()

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Tạo tài khoản mới',
      }),
    )

    await waitFor(() => {
      expect(screen.getByTestId('register-state')).toHaveTextContent(
        '"invitationToken":"secret-token"',
      )
      expect(screen.getByTestId('register-state')).toHaveTextContent(
        '"invitationAction":"accept"',
      )
    })
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
