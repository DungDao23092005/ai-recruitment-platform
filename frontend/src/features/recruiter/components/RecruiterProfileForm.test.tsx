import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { RecruiterProfileForm } from './RecruiterProfileForm'
import {
  createRecruiterProfile,
  getRecruiterProfile,
  updateRecruiterProfile,
} from '@/api/auth'

vi.mock('@/api/auth', () => ({
  createRecruiterProfile: vi.fn(),
  getRecruiterProfile: vi.fn(),
  updateRecruiterProfile: vi.fn(),
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
      expect(
        screen.getByLabelText('Họ và tên'),
      ).toHaveValue('Trần Thị Bích')
      expect(screen.getByLabelText('Vị trí')).toHaveValue(
        'Trưởng phòng Tuyển dụng',
      )
      expect(screen.getByLabelText('Mã công ty (tùy chọn)')).toHaveValue(
        'company-1',
      )
    })
  })

  it('shows an empty form when no profile exists', async () => {
    mockedGet.mockRejectedValue(notFoundError())

    render(<RecruiterProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('')
      expect(screen.getByLabelText('Vị trí')).toHaveValue('')
      expect(screen.getByLabelText('Mã công ty (tùy chọn)')).toHaveValue('')
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
        company_id: 'company-1',
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

    fireEvent.change(screen.getByLabelText('Mã công ty (tùy chọn)'), {
      target: { value: 'company-b' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Bạn không có quyền liên kết với công ty này.'),
      ).toBeInTheDocument()
    })
  })
})