import { render, act, waitFor, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { WorkspaceProvider, useWorkspace } from './WorkspaceContext'
import * as workspacesApi from '@/api/workspaces'
import { useAuth } from '@/contexts/AuthContext'
import type { Workspace } from '@/types/workspace'

vi.mock('@/api/workspaces')
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

const mockWorkspaces: Workspace[] = [
  {
    company_id: 'c-1',
    company_name: 'Company One',
    company_slug: 'company-one',
    role: 'recruiter',
    is_platform_admin: false,
  },
  {
    company_id: 'c-2',
    company_name: 'Company Two',
    company_slug: 'company-two',
    role: 'admin',
    is_platform_admin: false,
  },
]

function TestConsumer() {
  const { selectedCompanyId, workspaces, isLoading } = useWorkspace()
  return (
    <div>
      <span data-testid="selected">{selectedCompanyId ?? 'none'}</span>
      <span data-testid="count">{workspaces.length}</span>
      <span data-testid="loading">{isLoading ? 'loading' : 'idle'}</span>
    </div>
  )
}

describe('WorkspaceContext', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(useAuth).mockReturnValue({
      currentUser: { id: 'u-1', email: 'test@example.com', role: 'recruiter' } as any,
      isAuthenticated: true,
      isLoading: false,
      token: 'mock-token',
      login: vi.fn(),
      logout: vi.fn(),
    })
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('revoking the selected workspace switches to another valid workspace', async () => {
    localStorage.setItem('ai_recruitment_company_id', 'c-1')
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce(mockWorkspaces)

    render(
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('c-1')
      expect(screen.getByTestId('count')).toHaveTextContent('2')
    })

    // Mock next response after revocation: c-1 is gone, only c-2 remains
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce([mockWorkspaces[1]])

    act(() => {
      window.dispatchEvent(
        new CustomEvent('workspace:revoked', {
          detail: { company_id: 'c-1', membership_id: 'm-1' },
        }),
      )
    })

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('c-2')
      expect(screen.getByTestId('count')).toHaveTextContent('1')
    })

    expect(localStorage.getItem('ai_recruitment_company_id')).toBe('c-2')
  })

  it('revoking the selected workspace with no other workspace clears selection and localStorage', async () => {
    localStorage.setItem('ai_recruitment_company_id', 'c-1')
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce([mockWorkspaces[0]])

    render(
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('c-1')
      expect(screen.getByTestId('count')).toHaveTextContent('1')
    })

    // After revocation, no workspaces remain
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce([])

    act(() => {
      window.dispatchEvent(
        new CustomEvent('workspace:revoked', {
          detail: { company_id: 'c-1', membership_id: 'm-1' },
        }),
      )
    })

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('none')
      expect(screen.getByTestId('count')).toHaveTextContent('0')
    })

    expect(localStorage.getItem('ai_recruitment_company_id')).toBeNull()
  })

  it('revoking an inactive workspace preserves the current selection while refreshing the list', async () => {
    localStorage.setItem('ai_recruitment_company_id', 'c-1')
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce(mockWorkspaces)

    render(
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('c-1')
      expect(screen.getByTestId('count')).toHaveTextContent('2')
    })

    // c-2 is revoked, c-1 remains selected
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce([mockWorkspaces[0]])

    act(() => {
      window.dispatchEvent(
        new CustomEvent('workspace:revoked', {
          detail: { company_id: 'c-2', membership_id: 'm-2' },
        }),
      )
    })

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('c-1')
      expect(screen.getByTestId('count')).toHaveTextContent('1')
    })

    expect(localStorage.getItem('ai_recruitment_company_id')).toBe('c-1')
  })

  it('event listener is registered and cleaned up on unmount', () => {
    const addListenerSpy = vi.spyOn(window, 'addEventListener')
    const removeListenerSpy = vi.spyOn(window, 'removeEventListener')
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValue([])

    const { unmount } = render(
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>,
    )

    expect(addListenerSpy).toHaveBeenCalledWith('workspace:revoked', expect.any(Function))

    unmount()

    expect(removeListenerSpy).toHaveBeenCalledWith('workspace:revoked', expect.any(Function))
  })

  it('no logout occurs when workspace is revoked', async () => {
    localStorage.setItem('ai_recruitment_token', 'valid-token')
    localStorage.setItem('ai_recruitment_company_id', 'c-1')
    const logoutListener = vi.fn()
    window.addEventListener('ai-recruitment:logout', logoutListener)

    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce(mockWorkspaces)
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce([])

    render(
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('c-1')
    })

    act(() => {
      window.dispatchEvent(
        new CustomEvent('workspace:revoked', {
          detail: { company_id: 'c-1', membership_id: 'm-1' },
        }),
      )
    })

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('none')
    })

    expect(logoutListener).not.toHaveBeenCalled()
    expect(localStorage.getItem('ai_recruitment_token')).toBe('valid-token')

    window.removeEventListener('ai-recruitment:logout', logoutListener)
  })

  it('reloads workspaces when company:updated DOM event is dispatched', async () => {
    localStorage.setItem('ai_recruitment_company_id', 'c-1')
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce(mockWorkspaces)

    render(
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('selected')).toHaveTextContent('c-1')
      expect(screen.getByTestId('count')).toHaveTextContent('2')
    })

    const updatedWorkspaces = [
      { ...mockWorkspaces[0], company_name: 'Company One Updated' },
      mockWorkspaces[1],
    ]
    vi.mocked(workspacesApi.getWorkspaces).mockResolvedValueOnce(updatedWorkspaces)

    act(() => {
      window.dispatchEvent(
        new CustomEvent('company:updated', { detail: { entity_type: 'company' } }),
      )
    })

    await waitFor(() => {
      expect(workspacesApi.getWorkspaces).toHaveBeenCalledTimes(2)
    })
  })

  it('registers and cleans up company:updated event listener on unmount', () => {
    const addListenerSpy = vi.spyOn(window, 'addEventListener')
    const removeListenerSpy = vi.spyOn(window, 'removeEventListener')

    const { unmount } = render(
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>,
    )

    expect(addListenerSpy).toHaveBeenCalledWith('company:updated', expect.any(Function))

    unmount()

    expect(removeListenerSpy).toHaveBeenCalledWith('company:updated', expect.any(Function))
  })
})
