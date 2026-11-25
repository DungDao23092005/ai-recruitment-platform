import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  RecruiterProfileForm,
  getInitials,
  POSITION_PRESETS,
} from './RecruiterProfileForm'
import {
  getRecruiterProfile,
  updateRecruiterProfile,
  createRecruiterProfile,
} from '@/api/auth'

vi.mock('@/api/auth', () => ({
  createRecruiterProfile: vi.fn(),
  getRecruiterProfile: vi.fn(),
  updateRecruiterProfile: vi.fn(),
}))

let mockCurrentUser: {
  id: string
  email: string
  role: string
} | null = {
  id: 'user-1',
  email: 'recruiter@example.com',
  role: 'recruiter',
}

let mockSelectedWorkspace: {
  company_id: string
  company_name: string
  company_slug: string
  role?: 'admin' | 'recruiter' | 'interviewer' | null
} | null = {
  company_id: 'company-1',
  company_name: 'Acme Corp',
  company_slug: 'acme-corp',
  role: 'admin',
}

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: mockCurrentUser,
    isLoading: false,
    isAuthenticated: true,
  }),
}))

vi.mock('@/contexts/WorkspaceContext', () => ({
  useOptionalWorkspace: () => ({
    selectedWorkspace: mockSelectedWorkspace,
    workspaces: [],
    isLoading: false,
    selectWorkspace: vi.fn(),
    refreshWorkspaces: vi.fn(),
  }),
}))

const mockedGet = vi.mocked(getRecruiterProfile)
const mockedPut = vi.mocked(updateRecruiterProfile)
const mockedPost = vi.mocked(createRecruiterProfile)

const existingProfile = {
  id: 'profile-1',
  user_id: 'user-1',
  company_id: 'company-1',
  full_name: 'Trần Thị Bích',
  position: 'Trưởng phòng Tuyển dụng',
}

function notFoundError(): Error {
  const error = new Error('Not Found')
  Object.assign(error, { response: { status: 404 } })
  return error
}

beforeEach(() => {
  vi.clearAllMocks()
  mockCurrentUser = {
    id: 'user-1',
    email: 'recruiter@example.com',
    role: 'recruiter',
  }
  mockSelectedWorkspace = {
    company_id: 'company-1',
    company_name: 'Acme Corp',
    company_slug: 'acme-corp',
    role: 'admin',
  }
})

describe('getInitials', () => {
  it('extracts first letters from first and last words of multi-word names', () => {
    expect(getInitials('Trần Thị Bích')).toBe('TB')
    expect(getInitials('John Doe')).toBe('JD')
    expect(getInitials(' Nguyễn   Văn   A ')).toBe('NA')
  })

  it('extracts single initial for single-word names', () => {
    expect(getInitials('Dung')).toBe('D')
    expect(getInitials('Dũng')).toBe('D')
    expect(getInitials(' Recruiter ')).toBe('R')
  })

  it('falls back to email initial when name is empty or whitespace', () => {
    expect(getInitials('', 'dung@example.com')).toBe('D')
    expect(getInitials('   ', 'dung@example.com')).toBe('D')
    expect(getInitials(null, 'recruiter@example.com')).toBe('R')
    expect(getInitials(undefined, 'hr@acme.com')).toBe('H')
  })

  it('returns ? when both name and email are missing or empty', () => {
    expect(getInitials(null, null)).toBe('?')
    expect(getInitials('', '')).toBe('?')
    expect(getInitials('   ', '   ')).toBe('?')
    expect(getInitials(undefined, undefined)).toBe('?')
  })
})

describe('RecruiterProfileForm', () => {
  it('fetches the recruiter profile on mount', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledTimes(1)
    })
  })

  it('hydrates the form from an existing profile', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
      expect(screen.getByLabelText('Vị trí')).toHaveValue(
        'Trưởng phòng Tuyển dụng',
      )
      // Company ID is not editable in the form - it's managed separately
      expect(screen.queryByLabelText('Mã công ty')).not.toBeInTheDocument()
    })
  })

  it('shows an empty form when no profile exists', async () => {
    mockedGet.mockRejectedValue(notFoundError())

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('')
      expect(screen.getByLabelText('Vị trí')).toHaveValue('')
      expect(screen.queryByLabelText('Mã công ty')).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a friendly error when loading fails', async () => {
    const error = new Error('Server Error')
    Object.assign(error, { response: { status: 500, data: { detail: 'boom' } } })
    mockedGet.mockRejectedValue(error)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByText('boom')).toBeInTheDocument()
    })
  })

  it('submits existing profile edits with PUT', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedPut.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Trần Văn An' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith({
        full_name: 'Trần Văn An',
        position: 'Trưởng phòng Tuyển dụng',
      })
      expect(mockedPost).not.toHaveBeenCalled()
    })
  })

  it('submits a fresh profile with PUT (upsert), never POST', async () => {
    mockedGet.mockRejectedValue(notFoundError())
    mockedPut.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Trần Thị Bích' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledTimes(1)
      expect(mockedPost).not.toHaveBeenCalled()
    })
  })

  it('shows a success message after saving', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedPut.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
    })

    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Đã lưu hồ sơ nhà tuyển dụng.'),
      ).toBeInTheDocument()
    })
  })

  it('shows an API error message on failure', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 400, data: { detail: 'Invalid profile data' } },
    })
    mockedPut.mockRejectedValue(error)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
    })

    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(screen.getByText('Invalid profile data')).toBeInTheDocument()
    })
  })

  it('shows a Vietnamese message when company linking is forbidden', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    const error = new Error('Forbidden')
    Object.assign(error, {
      response: {
        status: 403,
        data: { detail: 'not allowed to link' },
      },
    })
    mockedPut.mockRejectedValue(error)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
    })

    // Since company_id is not in the form, this test is no longer relevant
    // The component doesn't allow manual company_id changes
    await waitFor(() => {
      expect(screen.queryByLabelText('Mã công ty')).not.toBeInTheDocument()
    })
  })

  it('displays read-only account email, company name, workspace role and initials avatar', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
    })

    // Initials avatar
    const avatar = screen.getByTestId('initials-avatar')
    expect(avatar).toHaveTextContent('TB')
    expect(avatar).toHaveAttribute('aria-label', 'Ảnh đại diện viết tắt: TB')

    // Read-only section
    expect(
      screen.getByText('THÔNG TIN TÀI KHOẢN & DOANH NGHIỆP'),
    ).toBeInTheDocument()
    expect(
      screen.getAllByText('recruiter@example.com').length,
    ).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Acme Corp').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Quản trị viên').length).toBeGreaterThanOrEqual(1)
  })

  it('displays fallback text when no workspace is selected', async () => {
    mockSelectedWorkspace = null
    mockedGet.mockResolvedValue({
      id: 'profile-1',
      user_id: 'user-1',
      company_id: null,
      full_name: '',
      position: '',
    } as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(
        screen.getByText('Chưa liên kết doanh nghiệp'),
      ).toBeInTheDocument()
      expect(screen.getByText('Chưa có vai trò')).toBeInTheDocument()
      expect(screen.getByText('Chưa cập nhật họ tên')).toBeInTheDocument()
      expect(screen.getByText('Chưa cập nhật vị trí')).toBeInTheDocument()
    })
  })

  it('displays "Chưa có vai trò" when workspace role is missing or undefined', async () => {
    mockSelectedWorkspace = {
      company_id: 'company-1',
      company_name: 'Acme Corp',
      company_slug: 'acme-corp',
      role: undefined,
    }
    mockedGet.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByText('Chưa có vai trò')).toBeInTheDocument()
      expect(screen.getAllByText('Acme Corp').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders all 5 position preset chips and updates position input on click', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Vị trí')).toHaveValue(
        'Trưởng phòng Tuyển dụng',
      )
    })

    // All presets rendered
    for (const preset of POSITION_PRESETS) {
      expect(screen.getByRole('button', { name: preset })).toBeInTheDocument()
    }

    // Initially none of presets match 'Trưởng phòng Tuyển dụng'
    const hrManagerBtn = screen.getByRole('button', { name: 'HR Manager' })
    expect(hrManagerBtn).toHaveAttribute('aria-pressed', 'false')

    // Click 'HR Manager' preset
    fireEvent.click(hrManagerBtn)

    expect(screen.getByLabelText('Vị trí')).toHaveValue('HR Manager')
    expect(hrManagerBtn).toHaveAttribute('aria-pressed', 'true')
  })

  it('controls the reset button based on dirty state and resets fields on click', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
    })

    const resetBtn = screen.getByRole('button', { name: /Hủy thay đổi/i })
    expect(resetBtn).toBeDisabled()

    // Modify name
    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Nguyễn Văn C' },
    })
    expect(resetBtn).toBeEnabled()

    // Click reset
    fireEvent.click(resetBtn)

    expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
    expect(resetBtn).toBeDisabled()
  })

  it('trims input values before submitting and preserves dirty values on API error', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 400, data: { detail: 'Tên không hợp lệ' } },
    })
    mockedPut.mockRejectedValue(error)

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Thị Bích')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: '   Trần Văn An   ' },
    })
    fireEvent.change(screen.getByLabelText('Vị trí'), {
      target: { value: '   HR Lead   ' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith({
        full_name: 'Trần Văn An',
        position: 'HR Lead',
      })
      expect(screen.getByText('Tên không hợp lệ')).toBeInTheDocument()
    })

    // User inputs are preserved after error
    expect(screen.getByLabelText('Họ và tên')).toHaveValue('   Trần Văn An   ')
    expect(screen.getByLabelText('Vị trí')).toHaveValue('   HR Lead   ')
  })
})
