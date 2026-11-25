import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  CandidateProfileForm,
  getInitials,
  TITLE_PRESETS,
} from './CandidateProfileForm'
import {
  createCandidateProfile,
  getCandidateProfile,
  updateCandidateProfile,
} from '@/api/auth'

vi.mock('@/api/auth', () => ({
  createCandidateProfile: vi.fn(),
  getCandidateProfile: vi.fn(),
  updateCandidateProfile: vi.fn(),
}))

let mockCurrentUser: {
  id: string
  email: string
  role: string
} | null = {
  id: 'user-1',
  email: 'candidate@example.com',
  role: 'candidate',
}

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: mockCurrentUser,
    isLoading: false,
    isAuthenticated: true,
  }),
}))

const mockedGet = vi.mocked(getCandidateProfile)
const mockedPut = vi.mocked(updateCandidateProfile)
const mockedPost = vi.mocked(createCandidateProfile)

const existingProfile = {
  id: 'profile-1',
  user_id: 'user-1',
  full_name: 'Nguyễn Văn An',
  phone: '+84 900 123 456',
  title: 'Senior Frontend Engineer',
}

function notFoundError(): Error {
  const error = new Error('Not Found')
  Object.assign(error, { response: { status: 404 } })
  return error
}

function renderComponent() {
  return render(
    <MemoryRouter>
      <CandidateProfileForm />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockCurrentUser = {
    id: 'user-1',
    email: 'candidate@example.com',
    role: 'candidate',
  }
})

describe('getInitials', () => {
  it('extracts first letters from first and last words of multi-word names', () => {
    expect(getInitials('Nguyễn Văn An')).toBe('NA')
    expect(getInitials('Trần Thị Bích')).toBe('TB')
    expect(getInitials(' John   Doe ')).toBe('JD')
  })

  it('extracts single initial for single-word names', () => {
    expect(getInitials('Dung')).toBe('D')
    expect(getInitials('Dũng')).toBe('D')
    expect(getInitials(' Candidate ')).toBe('C')
  })

  it('falls back to email initial when name is empty or whitespace', () => {
    expect(getInitials('', 'candidate@example.com')).toBe('C')
    expect(getInitials('   ', 'dung@example.com')).toBe('D')
    expect(getInitials(null, 'alex@company.org')).toBe('A')
    expect(getInitials(undefined, 'dev@example.vn')).toBe('D')
  })

  it('returns ? when both name and email are missing or empty', () => {
    expect(getInitials(null, null)).toBe('?')
    expect(getInitials('', '')).toBe('?')
    expect(getInitials('   ', '   ')).toBe('?')
    expect(getInitials(undefined, undefined)).toBe('?')
  })
})

describe('CandidateProfileForm - Loading and Hydration', () => {
  it('fetches the candidate profile on mount', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledTimes(1)
    })
  })

  it('hydrates the form from an existing profile', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
      expect(screen.getByLabelText('Số điện thoại')).toHaveValue(
        '+84 900 123 456',
      )
      expect(
        screen.getByLabelText('Vị trí / Chức danh mục tiêu'),
      ).toHaveValue('Senior Frontend Engineer')
    })
  })

  it('shows an empty form when no profile exists (404)', async () => {
    mockedGet.mockRejectedValue(notFoundError())

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('')
      expect(screen.getByLabelText('Số điện thoại')).toHaveValue('')
      expect(
        screen.getByLabelText('Vị trí / Chức danh mục tiêu'),
      ).toHaveValue('')
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a friendly error when loading fails', async () => {
    const error = new Error('Server Error')
    Object.assign(error, { response: { status: 500, data: { detail: 'boom' } } })
    mockedGet.mockRejectedValue(error)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('boom')).toBeInTheDocument()
    })
  })
})

describe('CandidateProfileForm - Read-Only Context and Summary', () => {
  it('displays read-only account email and candidate role badge in summary and context cards', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    // Initials avatar
    const avatar = screen.getByTestId('initials-avatar')
    expect(avatar).toHaveTextContent('NA')
    expect(avatar).toHaveAttribute('aria-label', 'Ảnh đại diện viết tắt: NA')

    // Read-only section
    expect(screen.getByText('THÔNG TIN TÀI KHOẢN')).toBeInTheDocument()
    expect(
      screen.getAllByText('candidate@example.com').length,
    ).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Ứng viên').length).toBeGreaterThanOrEqual(1)
  })

  it('displays fallback text when profile values are empty', async () => {
    mockedGet.mockRejectedValue(notFoundError())

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('Chưa cập nhật họ tên')).toBeInTheDocument()
      expect(
        screen.getByText('Chưa cập nhật chức danh mục tiêu'),
      ).toBeInTheDocument()
    })
  })

  it('ensures read-only values cannot be edited and are not included in PUT payload', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedPut.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Trần Thị Bích' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith({
        full_name: 'Trần Thị Bích',
        phone: '+84 900 123 456',
        title: 'Senior Frontend Engineer',
      })
      expect(mockedPut).not.toHaveBeenCalledWith(
        expect.objectContaining({ email: expect.anything() }),
      )
      expect(mockedPut).not.toHaveBeenCalledWith(
        expect.objectContaining({ role: expect.anything() }),
      )
    })
  })
})

describe('CandidateProfileForm - Position Presets', () => {
  it('renders all five approved title presets', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    for (const preset of TITLE_PRESETS) {
      expect(screen.getByRole('button', { name: preset })).toBeInTheDocument()
    }
  })

  it('clicking a preset updates the title input and its aria-pressed state', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(
        screen.getByLabelText('Vị trí / Chức danh mục tiêu'),
      ).toHaveValue('Senior Frontend Engineer')
    })

    const devOpsBtn = screen.getByRole('button', { name: 'DevOps Engineer' })
    expect(devOpsBtn).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(devOpsBtn)

    expect(screen.getByLabelText('Vị trí / Chức danh mục tiêu')).toHaveValue(
      'DevOps Engineer',
    )
    expect(devOpsBtn).toHaveAttribute('aria-pressed', 'true')
  })

  it('supports custom title entry alongside presets', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(
        screen.getByLabelText('Vị trí / Chức danh mục tiêu'),
      ).toHaveValue('Senior Frontend Engineer')
    })

    fireEvent.change(screen.getByLabelText('Vị trí / Chức danh mục tiêu'), {
      target: { value: 'Lead System Architect' },
    })

    expect(screen.getByLabelText('Vị trí / Chức danh mục tiêu')).toHaveValue(
      'Lead System Architect',
    )
    for (const preset of TITLE_PRESETS) {
      expect(screen.getByRole('button', { name: preset })).toHaveAttribute(
        'aria-pressed',
        'false',
      )
    }
  })
})

describe('CandidateProfileForm - Phone Validation', () => {
  it('accepts valid phone formats without showing validation error', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedPut.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    const validPhones = ['0901234567', '+84 900 123 456', '(024) 3838 9999']

    for (const validPhone of validPhones) {
      fireEvent.change(screen.getByLabelText('Số điện thoại'), {
        target: { value: validPhone },
      })
      fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

      await waitFor(() => {
        expect(
          screen.queryByText('Vui lòng nhập số điện thoại hợp lệ'),
        ).not.toBeInTheDocument()
      })
    }
  })

  it('displays error message for invalid phone formats and blocks submission', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.change(screen.getByLabelText('Số điện thoại'), {
      target: { value: 'abc090123' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Vui lòng nhập số điện thoại hợp lệ'),
      ).toBeInTheDocument()
      expect(mockedPut).not.toHaveBeenCalled()
    })
  })

  it('accepts empty phone as valid because the field is optional', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedPut.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.change(screen.getByLabelText('Số điện thoại'), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(
        screen.queryByText('Vui lòng nhập số điện thoại hợp lệ'),
      ).not.toBeInTheDocument()
      expect(mockedPut).toHaveBeenCalledWith({
        full_name: 'Nguyễn Văn An',
        phone: null,
        title: 'Senior Frontend Engineer',
      })
    })
  })
})

describe('CandidateProfileForm - Dirty State and Reset', () => {
  it('disables reset button when form is clean', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    expect(screen.getByRole('button', { name: /Hủy thay đổi/i })).toBeDisabled()
  })

  it('enables reset button when any editable field changes', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    const resetBtn = screen.getByRole('button', { name: /Hủy thay đổi/i })
    expect(resetBtn).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Nguyễn Văn B' },
    })
    expect(resetBtn).toBeEnabled()

    fireEvent.click(resetBtn)
    expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    expect(resetBtn).toBeDisabled()
  })

  it('restores all initial values when reset button is clicked', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Modified Name' },
    })
    fireEvent.change(screen.getByLabelText('Số điện thoại'), {
      target: { value: '0911222333' },
    })
    fireEvent.change(screen.getByLabelText('Vị trí / Chức danh mục tiêu'), {
      target: { value: 'Backend Developer' },
    })

    const resetBtn = screen.getByRole('button', { name: /Hủy thay đổi/i })
    expect(resetBtn).toBeEnabled()

    fireEvent.click(resetBtn)

    expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    expect(screen.getByLabelText('Số điện thoại')).toHaveValue('+84 900 123 456')
    expect(screen.getByLabelText('Vị trí / Chức danh mục tiêu')).toHaveValue(
      'Senior Frontend Engineer',
    )
    expect(resetBtn).toBeDisabled()
  })

  it('updates the dirty baseline on successful save', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedPut.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Trần Thị Bích' },
    })
    const resetBtn = screen.getByRole('button', { name: /Hủy thay đổi/i })
    expect(resetBtn).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Đã lưu hồ sơ ứng viên.'),
      ).toBeInTheDocument()
      expect(resetBtn).toBeDisabled()
    })
  })
})

describe('CandidateProfileForm - Submission and Failure Handling', () => {
  it('requires full name and blocks submission when empty', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Vui lòng nhập họ và tên'),
      ).toBeInTheDocument()
      expect(mockedPut).not.toHaveBeenCalled()
    })
  })

  it('submits trimmed values with PUT (upsert), never POST', async () => {
    mockedGet.mockRejectedValue(notFoundError())
    mockedPut.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: '   Nguyễn Văn An   ' },
    })
    fireEvent.change(screen.getByLabelText('Số điện thoại'), {
      target: { value: '   0901234567   ' },
    })
    fireEvent.change(screen.getByLabelText('Vị trí / Chức danh mục tiêu'), {
      target: { value: '   Full Stack Developer   ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledTimes(1)
      expect(mockedPut).toHaveBeenCalledWith({
        full_name: 'Nguyễn Văn An',
        phone: '0901234567',
        title: 'Full Stack Developer',
      })
      expect(mockedPost).not.toHaveBeenCalled()
    })
  })

  it('shows API error message on failure and preserves dirty inputs', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 400, data: { detail: 'Dữ liệu không hợp lệ' } },
    })
    mockedPut.mockRejectedValue(error)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Trần Văn C' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(screen.getByText('Dữ liệu không hợp lệ')).toBeInTheDocument()
    })

    // User inputs are preserved after error
    expect(screen.getByLabelText('Họ và tên')).toHaveValue('Trần Văn C')
    expect(screen.getByRole('button', { name: /Hủy thay đổi/i })).toBeEnabled()
  })
})

describe('CandidateProfileForm - CV Context Card', () => {
  it('renders CV and AI matching context card with accessible link to /candidate/cv-upload', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderComponent()

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    expect(
      screen.getByText('Quản lý CV & Hồ sơ ứng tuyển'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Tải lên CV để hệ thống phân tích kỹ năng, kinh nghiệm và đề xuất các vị trí tuyển dụng phù hợp.',
      ),
    ).toBeInTheDocument()

    const cvLink = screen.getByRole('link', { name: /Quản lý CV/i })
    expect(cvLink).toBeInTheDocument()
    expect(cvLink).toHaveAttribute('href', '/candidate/cv-upload')
  })
})
