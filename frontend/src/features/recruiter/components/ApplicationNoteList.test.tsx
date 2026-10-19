import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplicationNoteList } from './ApplicationNoteList'
import * as applicationsApi from '@/api/applications'
import { useAuth } from '@/contexts/AuthContext'
import type { ApplicationNote } from '@/types/application'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('@/api/applications', () => ({
  listApplicationNotes: vi.fn(),
  createApplicationNote: vi.fn(),
  updateApplicationNote: vi.fn(),
  deleteApplicationNote: vi.fn(),
}))

const mockedList = vi.mocked(applicationsApi.listApplicationNotes)
const mockedCreate = vi.mocked(applicationsApi.createApplicationNote)
const mockedUpdate = vi.mocked(applicationsApi.updateApplicationNote)
const mockedDelete = vi.mocked(applicationsApi.deleteApplicationNote)
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

const ownNote: ApplicationNote = {
  id: 'note-1',
  application_id: 'app-1',
  author_id: 'user-1',
  content: 'Ứng viên phản hồi tốt',
  created_at: '2026-02-01T10:00:00Z',
  updated_at: '2026-02-01T10:00:00Z',
}

const otherNote: ApplicationNote = {
  id: 'note-2',
  application_id: 'app-1',
  author_id: 'user-2',
  content: 'Cần kiểm tra thêm',
  created_at: '2026-02-02T10:00:00Z',
  updated_at: '2026-02-02T10:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUser()
})

describe('ApplicationNoteList', () => {
  it('renders notes with author labels', async () => {
    mockedList.mockResolvedValue([ownNote, otherNote])

    render(<ApplicationNoteList applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Ứng viên phản hồi tốt')).toBeInTheDocument()
    })
    expect(screen.getByText('Cần kiểm tra thêm')).toBeInTheDocument()
    expect(screen.getByText('Bạn')).toBeInTheDocument()
    expect(screen.getByText('Đồng nghiệp')).toBeInTheDocument()
  })

  it('only exposes edit/delete controls for the author', async () => {
    mockedList.mockResolvedValue([ownNote, otherNote])

    render(<ApplicationNoteList applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Ứng viên phản hồi tốt')).toBeInTheDocument()
    })
    expect(screen.getAllByRole('button', { name: 'Sửa ghi chú' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Xóa ghi chú' })).toHaveLength(1)
  })

  it('creates a note and prepends it', async () => {
    mockedList.mockResolvedValue([])
    mockedCreate.mockResolvedValue({
      ...ownNote,
      id: 'note-3',
      content: 'Ghi chú mới',
    })

    render(<ApplicationNoteList applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Chưa có ghi chú nội bộ')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Thêm ghi chú nội bộ'), {
      target: { value: 'Ghi chú mới' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thêm ghi chú' }))

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalledWith('app-1', 'Ghi chú mới')
      expect(screen.getByText('Ghi chú mới')).toBeInTheDocument()
    })
  })

  it('does not submit a blank note', async () => {
    mockedList.mockResolvedValue([])

    render(<ApplicationNoteList applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Chưa có ghi chú nội bộ')).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: 'Thêm ghi chú' })).toBeDisabled()
    expect(mockedCreate).not.toHaveBeenCalled()
  })

  it('deletes a note after confirmation', async () => {
    mockedList.mockResolvedValue([ownNote])
    mockedDelete.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApplicationNoteList applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Ứng viên phản hồi tốt')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Xóa ghi chú' }))

    await waitFor(() => {
      expect(mockedDelete).toHaveBeenCalledWith('app-1', 'note-1')
      expect(screen.queryByText('Ứng viên phản hồi tốt')).not.toBeInTheDocument()
    })
  })

  it('updates a note inline', async () => {
    mockedList.mockResolvedValue([ownNote])
    mockedUpdate.mockResolvedValue({ ...ownNote, content: 'Đã cập nhật' })

    render(<ApplicationNoteList applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Ứng viên phản hồi tốt')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Sửa ghi chú' }))
    fireEvent.change(screen.getByLabelText('Chỉnh sửa ghi chú'), {
      target: { value: 'Đã cập nhật' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalledWith('app-1', 'note-1', 'Đã cập nhật')
      expect(screen.getByText('Đã cập nhật')).toBeInTheDocument()
    })
  })
})
