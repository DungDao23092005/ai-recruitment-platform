import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { WorkspaceMembersPage } from './WorkspaceMembersPage'
import * as workspacesApi from '@/api/workspaces'
import { useAuth } from '@/contexts/AuthContext'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import type { WorkspaceMember, WorkspaceInvitation } from '@/types/workspace'

vi.mock('@/api/workspaces')

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: vi.fn(),
}))

describe('WorkspaceMembersPage', () => {
  const mockCurrentUser = {
    id: 'user-admin-1',
    email: 'admin@company.com',
    role: 'recruiter',
  }

  const mockAdminWorkspace = {
    company_id: 'company-1',
    company_name: 'TechNova AI',
    company_slug: 'technova-ai',
    role: 'admin',
    is_platform_admin: false,
  }

  const mockRefreshWorkspaces = vi.fn().mockResolvedValue([])

  const mockMembers: WorkspaceMember[] = [
    {
      membership_id: 'mem-1',
      user_id: 'user-admin-1',
      email: 'admin@company.com',
      full_name: 'Admin User',
      role: 'admin',
      status: 'active',
      is_owner: true,
      joined_at: '2026-01-01T00:00:00Z',
    },
    {
      membership_id: 'mem-2',
      user_id: 'user-recruiter-2',
      email: 'recruiter@company.com',
      full_name: 'Nguyen Van Recruiter',
      role: 'recruiter',
      status: 'active',
      is_owner: false,
      joined_at: '2026-02-01T00:00:00Z',
    },
  ]

  const mockInvitations: WorkspaceInvitation[] = [
    {
      id: 'inv-1',
      company_id: 'company-1',
      company_name: 'TechNova AI',
      company_slug: 'technova-ai',
      email: 'pending@example.com',
      role: 'interviewer',
      status: 'pending',
      expires_at: '2026-12-31T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
      can_accept: true,
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({
      currentUser: mockCurrentUser as any,
      isAuthenticated: true,
      isLoading: false,
      token: 'mock-token',
      login: vi.fn(),
      logout: vi.fn(),
    })
    vi.mocked(useWorkspace).mockReturnValue({
      selectedWorkspace: mockAdminWorkspace as any,
      workspaces: [mockAdminWorkspace as any],
      refreshWorkspaces: mockRefreshWorkspaces,
      selectWorkspace: vi.fn(),
      isLoading: false,
      error: null,
    })
    vi.mocked(workspacesApi.getWorkspaceMembers).mockResolvedValue(mockMembers)
    vi.mocked(workspacesApi.getWorkspaceInvitations).mockResolvedValue(mockInvitations)
    vi.mocked(workspacesApi.revokeWorkspaceMember).mockResolvedValue({ success: true } as any)
    vi.mocked(workspacesApi.revokeWorkspaceInvitation).mockResolvedValue({ success: true } as any)
  })

  const renderComponent = () => {
    return render(
      <MemoryRouter>
        <WorkspaceMembersPage />
      </MemoryRouter>,
    )
  }

  describe('Member Revocation Modal UX', () => {
    it('opens revocation modal with member details and consequence text; does NOT call window.confirm', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm')
      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('Nguyen Van Recruiter')).toBeInTheDocument()
      })

      // Active member who is not current user has "Thu hồi" button
      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      // First revoke button is for member Nguyen Van Recruiter
      fireEvent.click(revokeButtons[0])

      // Verify window.confirm was NOT called
      expect(confirmSpy).not.toHaveBeenCalled()

      // Modal is presented
      const modal = screen.getByRole('dialog', { name: 'Thu hồi quyền truy cập thành viên' })
      expect(modal).toBeInTheDocument()
      expect(within(modal).getByText('Thành viên này sẽ mất quyền truy cập vào không gian làm việc của công ty.')).toBeInTheDocument()
      expect(within(modal).getByText('Nguyen Van Recruiter')).toBeInTheDocument()
      expect(within(modal).getByText('recruiter@company.com')).toBeInTheDocument()
      expect(within(modal).getByRole('button', { name: 'Thu hồi quyền truy cập' })).toBeInTheDocument()
      expect(within(modal).getByRole('button', { name: 'Hủy' })).toBeInTheDocument()

      confirmSpy.mockRestore()
    })

    it('cancels member revocation and closes modal without calling API', async () => {
      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('Nguyen Van Recruiter')).toBeInTheDocument()
      })

      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      fireEvent.click(revokeButtons[0])

      expect(screen.getByRole('dialog', { name: 'Thu hồi quyền truy cập thành viên' })).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: 'Thu hồi quyền truy cập thành viên' })).not.toBeInTheDocument()
      })

      expect(workspacesApi.revokeWorkspaceMember).not.toHaveBeenCalled()
    })

    it('confirms member revocation, calls revokeWorkspaceMember and refreshes data', async () => {
      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('Nguyen Van Recruiter')).toBeInTheDocument()
      })

      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      fireEvent.click(revokeButtons[0])

      const confirmBtn = screen.getByRole('button', { name: 'Thu hồi quyền truy cập' })
      fireEvent.click(confirmBtn)

      await waitFor(() => {
        expect(workspacesApi.revokeWorkspaceMember).toHaveBeenCalledWith('mem-2')
        expect(workspacesApi.getWorkspaceMembers).toHaveBeenCalledTimes(2) // mount + reload
        expect(mockRefreshWorkspaces).toHaveBeenCalled()
        expect(screen.queryByRole('dialog', { name: 'Thu hồi quyền truy cập thành viên' })).not.toBeInTheDocument()
      })
    })

    it('prevents duplicate submissions and displays loading state during member revocation', async () => {
      let resolvePromise!: (val: any) => void
      const deferredPromise = new Promise((resolve) => {
        resolvePromise = resolve
      })
      vi.mocked(workspacesApi.revokeWorkspaceMember).mockReturnValue(deferredPromise as any)

      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('Nguyen Van Recruiter')).toBeInTheDocument()
      })

      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      fireEvent.click(revokeButtons[0])

      const confirmBtn = screen.getByRole('button', { name: 'Thu hồi quyền truy cập' })
      const cancelBtn = screen.getByRole('button', { name: 'Hủy' })

      fireEvent.click(confirmBtn)

      // Buttons are disabled during submission
      expect(confirmBtn).toBeDisabled()
      expect(cancelBtn).toBeDisabled()

      // Attempting second click while in flight does not trigger another call
      fireEvent.click(confirmBtn)
      expect(workspacesApi.revokeWorkspaceMember).toHaveBeenCalledTimes(1)

      // Resolve API call
      resolvePromise({ success: true })

      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: 'Thu hồi quyền truy cập thành viên' })).not.toBeInTheDocument()
      })
    })

    it('displays API error inside modal when member revocation fails', async () => {
      vi.mocked(workspacesApi.revokeWorkspaceMember).mockRejectedValueOnce({
        response: { data: { detail: 'Không thể thu hồi thành viên quản trị cuối cùng.' } },
      })

      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('Nguyen Van Recruiter')).toBeInTheDocument()
      })

      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      fireEvent.click(revokeButtons[0])

      const confirmBtn = screen.getByRole('button', { name: 'Thu hồi quyền truy cập' })
      fireEvent.click(confirmBtn)

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
        expect(screen.getByText('Không thể thu hồi thành viên quản trị cuối cùng.')).toBeInTheDocument()
      })

      // Modal stays open so user can inspect error
      expect(screen.getByRole('dialog', { name: 'Thu hồi quyền truy cập thành viên' })).toBeInTheDocument()
    })
  })

  describe('Invitation Revocation Modal UX', () => {
    it('opens revocation modal with invitation details and consequence text; does NOT call window.confirm', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm')
      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('pending@example.com')).toBeInTheDocument()
      })

      // The second "Thu hồi" button is in the invitations section
      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      // Last revoke button is for the pending invitation
      fireEvent.click(revokeButtons[revokeButtons.length - 1])

      expect(confirmSpy).not.toHaveBeenCalled()

      const modal = screen.getByRole('dialog', { name: 'Thu hồi lời mời tham gia' })
      expect(modal).toBeInTheDocument()
      expect(within(modal).getByText('Người nhận sẽ không thể sử dụng lời mời này để tham gia công ty nữa.')).toBeInTheDocument()
      expect(within(modal).getByText('pending@example.com')).toBeInTheDocument()
      expect(within(modal).getByText('Người phỏng vấn')).toBeInTheDocument()
      expect(within(modal).getByRole('button', { name: 'Thu hồi lời mời' })).toBeInTheDocument()
      expect(within(modal).getByRole('button', { name: 'Hủy' })).toBeInTheDocument()

      confirmSpy.mockRestore()
    })

    it('cancels invitation revocation and closes modal without calling API', async () => {
      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('pending@example.com')).toBeInTheDocument()
      })

      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      fireEvent.click(revokeButtons[revokeButtons.length - 1])

      expect(screen.getByRole('dialog', { name: 'Thu hồi lời mời tham gia' })).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: 'Thu hồi lời mời tham gia' })).not.toBeInTheDocument()
      })

      expect(workspacesApi.revokeWorkspaceInvitation).not.toHaveBeenCalled()
    })

    it('confirms invitation revocation, calls revokeWorkspaceInvitation and refreshes data', async () => {
      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('pending@example.com')).toBeInTheDocument()
      })

      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      fireEvent.click(revokeButtons[revokeButtons.length - 1])

      const confirmBtn = screen.getByRole('button', { name: 'Thu hồi lời mời' })
      fireEvent.click(confirmBtn)

      await waitFor(() => {
        expect(workspacesApi.revokeWorkspaceInvitation).toHaveBeenCalledWith('inv-1')
        expect(workspacesApi.getWorkspaceInvitations).toHaveBeenCalledTimes(2) // mount + reload
        expect(screen.queryByRole('dialog', { name: 'Thu hồi lời mời tham gia' })).not.toBeInTheDocument()
      })
    })

    it('prevents duplicate submissions and displays loading state during invitation revocation', async () => {
      let resolvePromise!: (val: any) => void
      const deferredPromise = new Promise((resolve) => {
        resolvePromise = resolve
      })
      vi.mocked(workspacesApi.revokeWorkspaceInvitation).mockReturnValue(deferredPromise as any)

      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('pending@example.com')).toBeInTheDocument()
      })

      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      fireEvent.click(revokeButtons[revokeButtons.length - 1])

      const confirmBtn = screen.getByRole('button', { name: 'Thu hồi lời mời' })
      const cancelBtn = screen.getByRole('button', { name: 'Hủy' })

      fireEvent.click(confirmBtn)

      // Buttons are disabled during submission
      expect(confirmBtn).toBeDisabled()
      expect(cancelBtn).toBeDisabled()

      // Attempting second click while in flight does not trigger another call
      fireEvent.click(confirmBtn)
      expect(workspacesApi.revokeWorkspaceInvitation).toHaveBeenCalledTimes(1)

      resolvePromise({ success: true })

      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: 'Thu hồi lời mời tham gia' })).not.toBeInTheDocument()
      })
    })

    it('displays API error inside modal when invitation revocation fails', async () => {
      vi.mocked(workspacesApi.revokeWorkspaceInvitation).mockRejectedValueOnce({
        response: { data: { detail: 'Lời mời không còn hiệu lực.' } },
      })

      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('pending@example.com')).toBeInTheDocument()
      })

      const revokeButtons = screen.getAllByRole('button', { name: /Thu hồi/i })
      fireEvent.click(revokeButtons[revokeButtons.length - 1])

      const confirmBtn = screen.getByRole('button', { name: 'Thu hồi lời mời' })
      fireEvent.click(confirmBtn)

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
        expect(screen.getByText('Lời mời không còn hiệu lực.')).toBeInTheDocument()
      })

      expect(screen.getByRole('dialog', { name: 'Thu hồi lời mời tham gia' })).toBeInTheDocument()
    })
  })

  describe('Access Control', () => {
    it('renders empty state when no workspace is selected', () => {
      vi.mocked(useWorkspace).mockReturnValue({
        selectedWorkspace: null,
        workspaces: [],
        refreshWorkspaces: mockRefreshWorkspaces,
        selectWorkspace: vi.fn(),
        isLoading: false,
        error: null,
      })

      renderComponent()

      expect(screen.getByText('Chưa chọn công ty')).toBeInTheDocument()
      expect(screen.getByText('Chọn công ty ở thanh điều hướng phía trên.')).toBeInTheDocument()
    })

    it('renders "Không đủ quyền" when user has non-manager role in workspace', () => {
      vi.mocked(useWorkspace).mockReturnValue({
        selectedWorkspace: {
          company_id: 'company-1',
          company_name: 'TechNova AI',
          company_slug: 'technova-ai',
          role: 'interviewer',
          is_platform_admin: false,
        } as any,
        workspaces: [],
        refreshWorkspaces: mockRefreshWorkspaces,
        selectWorkspace: vi.fn(),
        isLoading: false,
        error: null,
      })

      renderComponent()

      expect(screen.getByText('Không đủ quyền')).toBeInTheDocument()
      expect(screen.getByText('Bạn cần quyền quản trị viên hoặc nhà tuyển dụng của công ty này.')).toBeInTheDocument()
    })
  })

  describe('Redesigned Company Invitation Form', () => {
    it('renders header, email input with helper text, and all three role cards', async () => {
      renderComponent()

      expect(screen.getByText('Mời thành viên mới')).toBeInTheDocument()
      expect(screen.getByText('Gửi lời mời tham gia không gian làm việc của công ty qua email.')).toBeInTheDocument()
      expect(screen.getByLabelText(/Địa chỉ email đồng nghiệp/i)).toBeInTheDocument()
      expect(screen.getByText('Chỉ có thể mời đồng nghiệp đã có tài khoản trên hệ thống.')).toBeInTheDocument()
      expect(screen.getByText('Lời mời có thời hạn 7 ngày và chỉ dùng được một lần. Người được mời cần có tài khoản hợp lệ trong hệ thống để tham gia công ty.')).toBeInTheDocument()

      const radioGroup = screen.getByRole('radiogroup', { name: 'Chọn vai trò thành viên' })
      expect(radioGroup).toBeInTheDocument()

      const recruiterRole = screen.getByRole('radio', { name: /Nhà tuyển dụng/i })
      const interviewerRole = screen.getByRole('radio', { name: /Người phỏng vấn/i })
      const adminRole = screen.getByRole('radio', { name: /Quản trị viên/i })

      expect(recruiterRole).toBeInTheDocument()
      expect(interviewerRole).toBeInTheDocument()
      expect(adminRole).toBeInTheDocument()

      // Default role is recruiter
      expect(recruiterRole).toHaveAttribute('aria-checked', 'true')
      expect(interviewerRole).toHaveAttribute('aria-checked', 'false')
      expect(adminRole).toHaveAttribute('aria-checked', 'false')
    })

    it('clicking a role card updates the accessible selected state', async () => {
      renderComponent()

      const interviewerRole = screen.getByRole('radio', { name: /Người phỏng vấn/i })
      const recruiterRole = screen.getByRole('radio', { name: /Nhà tuyển dụng/i })

      fireEvent.click(interviewerRole)

      expect(interviewerRole).toHaveAttribute('aria-checked', 'true')
      expect(recruiterRole).toHaveAttribute('aria-checked', 'false')
    })

    it('supports keyboard navigation across role cards', async () => {
      renderComponent()

      const recruiterRole = screen.getByRole('radio', { name: /Nhà tuyển dụng/i })
      const interviewerRole = screen.getByRole('radio', { name: /Người phỏng vấn/i })
      const adminRole = screen.getByRole('radio', { name: /Quản trị viên/i })

      // ArrowRight from recruiter (index 0) moves to interviewer (index 1)
      fireEvent.keyDown(recruiterRole, { key: 'ArrowRight' })
      expect(interviewerRole).toHaveAttribute('aria-checked', 'true')

      // ArrowRight from interviewer moves to admin (index 2)
      fireEvent.keyDown(interviewerRole, { key: 'ArrowRight' })
      expect(adminRole).toHaveAttribute('aria-checked', 'true')

      // ArrowLeft from admin moves back to interviewer
      fireEvent.keyDown(adminRole, { key: 'ArrowLeft' })
      expect(interviewerRole).toHaveAttribute('aria-checked', 'true')
    })

    it('submits trimmed email and selected role, clears input, and displays success message', async () => {
      vi.mocked(workspacesApi.createWorkspaceInvitation).mockResolvedValueOnce({
        id: 'new-inv-1',
        email: 'colleague@example.com',
        role: 'admin',
      } as any)

      renderComponent()

      const emailInput = screen.getByLabelText(/Địa chỉ email đồng nghiệp/i)
      fireEvent.change(emailInput, { target: { value: '   colleague@example.com   ' } })

      const adminRole = screen.getByRole('radio', { name: /Quản trị viên/i })
      fireEvent.click(adminRole)

      const submitBtn = screen.getByRole('button', { name: /Gửi lời mời tham gia/i })
      fireEvent.click(submitBtn)

      await waitFor(() => {
        expect(workspacesApi.createWorkspaceInvitation).toHaveBeenCalledWith({
          email: 'colleague@example.com',
          role: 'admin',
        })
        expect(screen.getByRole('status')).toHaveTextContent('Đã gửi lời mời tham gia công ty.')
        expect(emailInput).toHaveValue('')
      })
    })

    it('prevents duplicate form submission during in-flight request', async () => {
      let resolvePromise!: (val: any) => void
      const deferred = new Promise((resolve) => {
        resolvePromise = resolve
      })
      vi.mocked(workspacesApi.createWorkspaceInvitation).mockReturnValue(deferred as any)

      renderComponent()

      const emailInput = screen.getByLabelText(/Địa chỉ email đồng nghiệp/i)
      fireEvent.change(emailInput, { target: { value: 'wait@example.com' } })

      const submitBtn = screen.getByRole('button', { name: /Gửi lời mời tham gia/i })
      fireEvent.click(submitBtn)

      expect(submitBtn).toBeDisabled()

      // Second click does not trigger another API call
      fireEvent.click(submitBtn)
      expect(workspacesApi.createWorkspaceInvitation).toHaveBeenCalledTimes(1)

      resolvePromise({ id: 'inv-ok' })
      await waitFor(() => {
        expect(submitBtn).not.toBeDisabled()
      })
    })

    it('displays API error inline inside the card and preserves entered email on failure', async () => {
      vi.mocked(workspacesApi.createWorkspaceInvitation).mockRejectedValueOnce({
        response: { data: { detail: 'A pending invitation already exists for this email' } },
      })

      renderComponent()

      const emailInput = screen.getByLabelText(/Địa chỉ email đồng nghiệp/i)
      fireEvent.change(emailInput, { target: { value: 'dup@example.com' } })

      const submitBtn = screen.getByRole('button', { name: /Gửi lời mời tham gia/i })
      fireEvent.click(submitBtn)

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('A pending invitation already exists for this email')
        expect(emailInput).toHaveValue('dup@example.com')
      })
    })

    it('displays localized unknown account error inline and preserves entered email', async () => {
      vi.mocked(workspacesApi.createWorkspaceInvitation).mockRejectedValueOnce({
        response: { status: 404, data: { detail: 'Tài khoản với email này không tồn tại trong hệ thống.' } },
      })

      renderComponent()

      const emailInput = screen.getByLabelText(/Địa chỉ email đồng nghiệp/i)
      fireEvent.change(emailInput, { target: { value: 'notfound@example.com' } })

      const submitBtn = screen.getByRole('button', { name: /Gửi lời mời tham gia/i })
      fireEvent.click(submitBtn)

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Tài khoản với email này không tồn tại trong hệ thống.')
        expect(emailInput).toHaveValue('notfound@example.com')
      })
    })
  })

  describe('Member Tabs and History Visibility', () => {
    const mixedMembers: WorkspaceMember[] = [
      {
        membership_id: 'mem-1',
        user_id: 'user-admin-1',
        email: 'admin@company.com',
        full_name: 'Admin User',
        role: 'admin',
        status: 'active',
        is_owner: true,
        joined_at: '2026-01-01T00:00:00Z',
      },
      {
        membership_id: 'mem-2',
        user_id: 'user-recruiter-2',
        email: 'recruiter@company.com',
        full_name: 'Nguyen Van Recruiter',
        role: 'recruiter',
        status: 'active',
        is_owner: false,
        joined_at: '2026-02-01T00:00:00Z',
      },
      {
        membership_id: 'mem-3',
        user_id: 'user-old-1',
        email: 'former1@company.com',
        full_name: 'Former Member 1',
        role: 'interviewer',
        status: 'revoked',
        is_owner: false,
        joined_at: '2026-01-05T00:00:00Z',
        revoked_at: '2026-02-10T12:00:00Z',
      },
      {
        membership_id: 'mem-4',
        user_id: 'user-old-2',
        email: 'former2@company.com',
        full_name: 'Former Member 2',
        role: 'recruiter',
        status: 'revoked',
        is_owner: false,
        joined_at: '2026-01-10T00:00:00Z',
        revoked_at: '2026-02-15T14:30:00Z',
      },
    ]

    it('renders both tabs with correct member counts', async () => {
      vi.mocked(workspacesApi.getWorkspaceMembers).mockResolvedValue(mixedMembers)
      renderComponent()

      await waitFor(() => {
        expect(
          screen.getByRole('tab', { name: 'Thành viên hiện tại (2)' })
        ).toBeInTheDocument()
        expect(
          screen.getByRole('tab', { name: 'Lịch sử đã thu hồi (2)' })
        ).toBeInTheDocument()
      })
    })

    it('displays active members with role controls and revoke button on active tab', async () => {
      vi.mocked(workspacesApi.getWorkspaceMembers).mockResolvedValue(mixedMembers)
      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('Nguyen Van Recruiter')).toBeInTheDocument()
      })

      // Active tab panel is active by default
      const panel = screen.getByRole('tabpanel', { name: 'Thành viên hiện tại (2)' })
      expect(panel).toBeInTheDocument()
      expect(within(panel).queryByText('Former Member 1')).not.toBeInTheDocument()

      // Active non-self member has role select and revoke button
      expect(
        within(panel).getByRole('combobox', { name: 'Vai trò của recruiter@company.com' })
      ).toBeInTheDocument()
      expect(
        within(panel).getByRole('button', { name: /Thu hồi/i })
      ).toBeInTheDocument()
    })

    it('switches to revoked tab, sorts by revoked_at desc, and is read-only', async () => {
      vi.mocked(workspacesApi.getWorkspaceMembers).mockResolvedValue(mixedMembers)
      renderComponent()

      await waitFor(() => {
        expect(screen.getByText('Nguyen Van Recruiter')).toBeInTheDocument()
      })

      const revokedTab = screen.getByRole('tab', { name: 'Lịch sử đã thu hồi (2)' })
      fireEvent.click(revokedTab)

      await waitFor(() => {
        expect(screen.getByText('Former Member 2')).toBeInTheDocument()
        expect(screen.getByText('Former Member 1')).toBeInTheDocument()
      })

      const revokedPanel = screen.getByRole('tabpanel', { name: 'Lịch sử đã thu hồi (2)' })
      expect(revokedPanel).toBeInTheDocument()

      // Active members are hidden on revoked tab
      expect(within(revokedPanel).queryByText('Nguyen Van Recruiter')).not.toBeInTheDocument()

      // Verify ordering: Former Member 2 (revoked Feb 15) comes before Former Member 1 (revoked Feb 10)
      const listItems = within(revokedPanel).getAllByRole('listitem')
      const texts = listItems.map((li) => li.textContent || '')
      const indexFormer2 = texts.findIndex((t) => t.includes('Former Member 2'))
      const indexFormer1 = texts.findIndex((t) => t.includes('Former Member 1'))
      expect(indexFormer2).toBeLessThan(indexFormer1)

      // Read-only: no role select and no revoke button on revoked tab
      expect(within(revokedPanel).queryByRole('combobox')).not.toBeInTheDocument()
      expect(within(revokedPanel).queryByRole('button', { name: /Thu hồi/i })).not.toBeInTheDocument()
    })

    it('renders empty states when there are no active or revoked members', async () => {
      vi.mocked(workspacesApi.getWorkspaceMembers).mockResolvedValue([])
      renderComponent()

      await waitFor(() => {
        expect(
          screen.getByText('Chưa có thành viên nào đang hoạt động.')
        ).toBeInTheDocument()
      })

      const revokedTab = screen.getByRole('tab', { name: 'Lịch sử đã thu hồi (0)' })
      fireEvent.click(revokedTab)

      await waitFor(() => {
        expect(
          screen.getByText('Chưa có thành viên nào bị thu hồi.')
        ).toBeInTheDocument()
      })
    })
  })
})
