import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { RecruiterJobEditPage } from './RecruiterJobEditPage'
import { getMyJobById } from '@/api/jobs'
import type { Job } from '@/types/job'

const mockJob: Job = {
  id: 'job-1',
  company_id: 'company-1',
  company_name: 'TechNova AI',
  title: 'Backend Engineer',
  description: 'Build robust APIs.',
  status: 'draft',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

vi.mock('@/api/jobs', () => ({
  getMyJobById: vi.fn(),
}))

const mockedGetMyJobById = vi.mocked(getMyJobById)

beforeEach(() => {
  vi.clearAllMocks()
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/recruiter/jobs/:id/edit" element={<RecruiterJobEditPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RecruiterJobEditPage', () => {
  it('loads the job and renders the edit form', async () => {
    mockedGetMyJobById.mockResolvedValue(mockJob)

    renderAt('/recruiter/jobs/job-1/edit')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Sửa tin tuyển dụng' }),
      ).toBeInTheDocument()
    })
    expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
    expect(
      screen.getByRole('button', { name: /Lưu thay đổi/i }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Tiêu đề công việc')).toHaveValue(
      'Backend Engineer',
    )
  })

  it('shows an empty state when the job is not found', async () => {
    const error = new Error('Not Found')
    Object.assign(error, { response: { status: 404 } })
    mockedGetMyJobById.mockRejectedValue(error)

    renderAt('/recruiter/jobs/job-missing/edit')

    await waitFor(() => {
      expect(
        screen.getByText('Không tìm thấy tin tuyển dụng'),
      ).toBeInTheDocument()
    })
  })

  it('shows an error banner with retry on load failure', async () => {
    const error = new Error('Network Error')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Máy chủ lỗi.' } },
    })
    mockedGetMyJobById.mockRejectedValueOnce(error)
    mockedGetMyJobById.mockResolvedValueOnce(mockJob)

    renderAt('/recruiter/jobs/job-1/edit')

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledTimes(2)
      expect(
        screen.getByRole('button', { name: /Lưu thay đổi/i }),
      ).toBeInTheDocument()
    })
  })
})