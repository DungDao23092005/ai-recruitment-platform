import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { ResumeUploadPage } from './ResumeUploadPage'
import { getCandidateProfile } from '@/api/auth'
import { getMyResume, parseResume } from '@/api/ai'
import type { ResumeRead } from '@/types/ai'

vi.mock('@/api/auth', () => ({
  getCandidateProfile: vi.fn(),
}))

vi.mock('@/api/ai', () => ({
  getMyResume: vi.fn(),
  parseResume: vi.fn(),
}))

const mockedGet = vi.mocked(getCandidateProfile)
const mockedGetResume = vi.mocked(getMyResume)
const mockedParseResume = vi.mocked(parseResume)

const existingProfile = {
  id: 'profile-1',
  user_id: 'user-1',
  full_name: 'Nguyễn Văn An',
  phone: '+84 900 123 456',
  title: 'Senior Frontend Engineer',
}

const savedResume: ResumeRead = {
  id: 'resume-1',
  candidate_id: 'profile-1',
  title: 'cv.pdf',
  is_primary: true,
  parsed_data: {
    full_name: 'Nguyễn Văn An',
    email: 'an@example.com',
    phone: null,
    title: 'Senior Frontend Engineer',
    summary: 'Dự án React lớn',
    total_years_experience: 5,
    skills: ['React', 'TypeScript'],
    experiences: [],
    education: [],
    certifications: [],
    languages: [],
  },
  created_at: '2026-08-15T00:00:00Z',
  updated_at: '2026-08-15T00:00:00Z',
}

function notFoundError(): Error {
  const error = new Error('Not Found')
  Object.assign(error, { response: { status: 404 } })
  return error
}

function serverError(): Error {
  const error = new Error('Server Error')
  Object.assign(error, { response: { status: 500 } })
  return error
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedGetResume.mockRejectedValue(notFoundError())
})

afterEach(() => {
  vi.restoreAllMocks()
})

function renderPage() {
  return render(
    <MemoryRouter>
      <ResumeUploadPage />
    </MemoryRouter>,
  )
}

describe('ResumeUploadPage', () => {
  it('fetches the candidate profile on mount', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderPage()

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledTimes(1)
    })
  })

  it('shows the upload area when a profile exists without a resume', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Tải lên CV PDF' }),
      ).toBeInTheDocument()
    })
    expect(mockedGetResume).toHaveBeenCalledTimes(1)
  })

  it('disables upload while the profile is loading', async () => {
    let resolveGet!: (value: { id: string }) => void
    mockedGet.mockReturnValue(
      new Promise((resolve) => {
        resolveGet = resolve
      }) as never,
    )

    renderPage()

    expect(
      screen.queryByRole('button', { name: 'Tải lên CV PDF' }),
    ).not.toBeInTheDocument()

    resolveGet(existingProfile)
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Tải lên CV PDF' }),
      ).toBeInTheDocument()
    })
  })

  it('does not show upload while resume state is loading', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    let resolveResume!: (value: ResumeRead) => void
    mockedGetResume.mockReturnValue(
      new Promise((resolve) => {
        resolveResume = resolve
      }) as never,
    )

    renderPage()

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledTimes(1)
    })
    expect(
      screen.queryByRole('button', { name: 'Tải lên CV PDF' }),
    ).not.toBeInTheDocument()

    resolveResume(savedResume)
    await waitFor(() => {
      expect(screen.getByText('CV đã được tải lên')).toBeInTheDocument()
    })
  })

  it('gates upload when no profile exists and shows CTA', async () => {
    mockedGet.mockRejectedValue(notFoundError())

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Hồ sơ ứng viên chưa được tạo'),
      ).toBeInTheDocument()
    })
    expect(
      screen.getByText('Vui lòng tạo hồ sơ ứng viên trước khi tải CV.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Tải lên CV PDF' }),
    ).not.toBeInTheDocument()
    expect(mockedGetResume).not.toHaveBeenCalled()
  })

  it('navigates to the candidate profile page via CTA', async () => {
    mockedGet.mockRejectedValue(notFoundError())

    renderPage()

    await waitFor(() => {
      const link = screen.getByRole('link', {
        name: 'Tạo hồ sơ ứng viên',
      })
      expect(link).toHaveAttribute('href', '/candidate/profile')
    })
  })

  it('shows a friendly error when profile GET fails and retries', async () => {
    mockedGet
      .mockRejectedValueOnce(serverError())
      .mockResolvedValueOnce(existingProfile as never)

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Không thể tải thông tin hồ sơ ứng viên.'),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledTimes(2)
      expect(
        screen.getByRole('button', { name: 'Tải lên CV PDF' }),
      ).toBeInTheDocument()
    })
  })

  it('hydrates the parsed resume when a saved CV exists', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedGetResume.mockResolvedValue(savedResume as never)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('CV đã được tải lên')).toBeInTheDocument()
    })
    expect(screen.getByText('cv.pdf')).toBeInTheDocument()
    expect(screen.getByText('Nguyễn Văn An')).toBeInTheDocument()
    expect(screen.getByText('React')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Tải lên CV PDF' }),
    ).not.toBeInTheDocument()
  })

  it('shows a friendly resume error and retries', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedGetResume
      .mockRejectedValueOnce(serverError())
      .mockResolvedValueOnce(savedResume as never)

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Không thể tải thông tin CV đã tải lên.'),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedGetResume).toHaveBeenCalledTimes(2)
      expect(screen.getByText('CV đã được tải lên')).toBeInTheDocument()
    })
  })

  it('allows re-uploading a new CV via "Cập nhật CV"', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedGetResume.mockResolvedValue(savedResume as never)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('CV đã được tải lên')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Cập nhật CV' }))

    expect(
      screen.getByRole('button', { name: 'Tải lên CV PDF' }),
    ).toBeInTheDocument()
  })

  it('updates the UI immediately after a successful re-upload', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedGetResume.mockResolvedValue(savedResume as never)
    const newParsed = {
      ...(savedResume.parsed_data as object),
      full_name: 'Trần Thị Bích',
      skills: ['Vue', 'Node.js'],
    }
    mockedParseResume.mockResolvedValue(newParsed as never)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('CV đã được tải lên')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Cập nhật CV' }))

    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement
    const file = new File(['pdf'], 'new-cv.pdf', { type: 'application/pdf' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => {
      expect(mockedParseResume).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Trần Thị Bích')).toBeInTheDocument()
      expect(screen.getByText('Vue')).toBeInTheDocument()
    })
  })

  it('does not persist any CV data to localStorage', async () => {
    mockedGet.mockResolvedValue(existingProfile as never)
    mockedGetResume.mockResolvedValue(savedResume as never)
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('CV đã được tải lên')).toBeInTheDocument()
    })
    expect(setItemSpy).not.toHaveBeenCalled()
  })
})