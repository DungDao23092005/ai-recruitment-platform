import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { JobForm } from './JobForm'
import apiClient from '@/api/client'
import type { Job } from '@/types/job'

const mockJob: Job = {
  id: 'job-1',
  company_id: 'company-1',
  title: 'Senior Frontend Engineer',
  description: 'Build modern web applications with React.',
  status: 'draft',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

const mockedPost = vi.mocked(apiClient.post)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('JobForm', () => {
  it('requires a job title', async () => {
    render(<JobForm companyId="company-1" />)

    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(screen.getByText('Tiêu đề công việc là bắt buộc')).toBeInTheDocument()
    })
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it('requires a job description', async () => {
    render(<JobForm companyId="company-1" />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Senior Frontend Engineer' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Mô tả công việc là bắt buộc'),
      ).toBeInTheDocument()
    })
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it('submits job with company id', async () => {
    mockedPost.mockResolvedValue(mockJob as never)

    render(<JobForm companyId="company-1" />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Senior Frontend Engineer' },
    })
    fireEvent.change(screen.getByLabelText('Mô tả công việc'), {
      target: { value: 'Build modern web applications with React.' },
    })
    fireEvent.change(screen.getByLabelText('Hình thức làm việc'), {
      target: { value: 'remote' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/jobs', {
        company_id: 'company-1',
        title: 'Senior Frontend Engineer',
        description: 'Build modern web applications with React.',
        job_type: 'full_time',
        workplace_type: 'remote',
        location: null,
        status: 'draft',
      })
      expect(
        screen.getByText('Tạo tin tuyển dụng thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('calls onCreated with the created job', async () => {
    mockedPost.mockResolvedValue(mockJob as never)
    const onCreated = vi.fn()

    render(<JobForm companyId="company-1" onCreated={onCreated} />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Senior Frontend Engineer' },
    })
    fireEvent.change(screen.getByLabelText('Mô tả công việc'), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(mockJob)
    })
  })

  it('shows error message on API failure', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 400, data: { detail: 'Invalid job data' } },
    })
    mockedPost.mockRejectedValue(error)

    render(<JobForm companyId="company-1" />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Senior Frontend Engineer' },
    })
    fireEvent.change(screen.getByLabelText('Mô tả công việc'), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(screen.getByText('Invalid job data')).toBeInTheDocument()
    })
  })

  it('shows a friendly forbidden message when job creation is unauthorized', async () => {
    const error = new Error('Forbidden')
    Object.assign(error, {
      response: { status: 403, data: { detail: 'No permission' } },
    })
    mockedPost.mockRejectedValue(error)

    render(<JobForm companyId="company-1" />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Senior Frontend Engineer' },
    })
    fireEvent.change(screen.getByLabelText('Mô tả công việc'), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(
        screen.getByText(
          'Bạn không có quyền đăng tin tuyển dụng cho công ty này.',
        ),
      ).toBeInTheDocument()
    })
  })

  it('allows only draft and published status options', () => {
    render(<JobForm companyId="company-1" />)

    const statusSelect = screen.getByLabelText('Trạng thái')
    const options = Array.from(
      (statusSelect as HTMLSelectElement).options,
    ).map((option) => option.value)

    expect(options).toEqual(['draft', 'published'])
  })
})