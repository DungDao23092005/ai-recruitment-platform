import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplicationActivityTimeline } from './ApplicationActivityTimeline'
import * as applicationsApi from '@/api/applications'
import { useAuth } from '@/contexts/AuthContext'
import type { ApplicationActivity } from '@/types/application'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('@/api/applications', () => ({
  listApplicationActivities: vi.fn(),
}))

const mockedList = vi.mocked(applicationsApi.listApplicationActivities)
const mockedUseAuth = vi.mocked(useAuth)

function mockUser(id = 'user-1', role: 'recruiter' | 'admin' = 'recruiter') {
  mockedUseAuth.mockReturnValue({
    currentUser: {
      id,
      email: 'r@example.com',
      role,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    token: 'token',
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshCurrentUser: vi.fn(),
  })
}

const statusActivity: ApplicationActivity = {
  id: 'act-1',
  application_id: 'app-1',
  actor_id: 'user-1',
  action_type: 'status_changed',
  from_status: 'applied',
  to_status: 'under_review',
  note: null,
  metadata_json: null,
  created_at: '2026-02-01T10:00:00Z',
}

const withdrewActivity: ApplicationActivity = {
  id: 'act-2',
  application_id: 'app-1',
  actor_id: 'candidate-user',
  action_type: 'candidate_withdrew',
  from_status: 'under_review',
  to_status: 'withdrawn',
  note: null,
  metadata_json: null,
  created_at: '2026-02-02T10:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUser()
})

describe('ApplicationActivityTimeline', () => {
  it('renders a status change with actor and from/to labels', async () => {
    mockedList.mockResolvedValue([statusActivity])

    render(<ApplicationActivityTimeline applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Cập nhật trạng thái')).toBeInTheDocument()
    })
    expect(screen.getByText('Bạn')).toBeInTheDocument()
    expect(screen.getByText('Đã nộp')).toBeInTheDocument()
    expect(screen.getByText('Đang xem xét')).toBeInTheDocument()
  })

  it('labels candidate-driven events as Ứng viên', async () => {
    mockedList.mockResolvedValue([withdrewActivity])

    render(<ApplicationActivityTimeline applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Ứng viên đã rút đơn')).toBeInTheDocument()
    })
    expect(screen.getByText('Ứng viên')).toBeInTheDocument()
  })

  it('renders an empty state when there is no history', async () => {
    mockedList.mockResolvedValue([])

    render(<ApplicationActivityTimeline applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Chưa có hoạt động')).toBeInTheDocument()
    })
  })

  it('shows a permission message on 403 and can retry', async () => {
    const error = new Error('Forbidden')
    Object.assign(error, { response: { status: 403 } })
    mockedList.mockRejectedValueOnce(error).mockResolvedValueOnce([])

    render(<ApplicationActivityTimeline applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Bạn không có quyền xem lịch sử hoạt động',
      )
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedList).toHaveBeenCalledTimes(2)
      expect(screen.getByText('Chưa có hoạt động')).toBeInTheDocument()
    })
  })
})
