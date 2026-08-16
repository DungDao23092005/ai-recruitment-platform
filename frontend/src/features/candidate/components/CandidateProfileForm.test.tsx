import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { CandidateProfileForm } from './CandidateProfileForm'
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

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CandidateProfileForm', () => {
  it('fetches the candidate profile on mount', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    render(<CandidateProfileForm />)

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledTimes(1)
    })
  })

  it('hydrates the form from an existing profile', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    render(<CandidateProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
      expect(screen.getByLabelText('Số điện thoại')).toHaveValue(
        '+84 900 123 456',
      )
      expect(screen.getByLabelText('Vị trí / Chức danh')).toHaveValue(
        'Senior Frontend Engineer',
      )
    })
  })

  it('shows an empty form when no profile exists', async () => {
    mockedGet.mockRejectedValue(notFoundError())

    render(<CandidateProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('')
      expect(screen.getByLabelText('Số điện thoại')).toHaveValue('')
      expect(screen.getByLabelText('Vị trí / Chức danh')).toHaveValue('')
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a friendly error when loading fails', async () => {
    const error = new Error('Server Error')
    Object.assign(error, { response: { status: 500, data: { detail: 'boom' } } })
    mockedGet.mockRejectedValue(error)

    render(<CandidateProfileForm />)

    await waitFor(() => {
      expect(screen.getByText('boom')).toBeInTheDocument()
    })
  })

  it('submits existing profile edits with PUT', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedPut.mockResolvedValue(existingProfile as never)

    render(<CandidateProfileForm />)

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
      expect(mockedPost).not.toHaveBeenCalled()
    })
  })

  it('submits a fresh profile with PUT (upsert), never POST', async () => {
    mockedGet.mockRejectedValue(notFoundError())
    mockedPut.mockResolvedValue(existingProfile as never)

    render(<CandidateProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('')
    })

    fireEvent.change(screen.getByLabelText('Họ và tên'), {
      target: { value: 'Nguyễn Văn An' },
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

    render(<CandidateProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Đã lưu hồ sơ ứng viên.'),
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

    render(<CandidateProfileForm />)

    await waitFor(() => {
      expect(screen.getByLabelText('Họ và tên')).toHaveValue('Nguyễn Văn An')
    })

    fireEvent.click(screen.getByRole('button', { name: /Lưu hồ sơ/i }))

    await waitFor(() => {
      expect(screen.getByText('Invalid profile data')).toBeInTheDocument()
    })
  })
})