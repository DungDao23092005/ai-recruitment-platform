import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { JobForm } from './JobForm'
import apiClient from '@/api/client'
import type { Job } from '@/types/job'

const mockJob: Job = {
  id: 'job-1',
  company_id: 'company-1',
  company_name: null,
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
      expect(mockedPost).toHaveBeenCalledWith(
        '/jobs',
        {
          company_id: 'company-1',
          title: 'Senior Frontend Engineer',
          description: 'Build modern web applications with React.',
          job_type: 'full_time',
          workplace_type: 'remote',
          location: null,
          status: 'draft',
          required_skills: [],
          preferred_skills: [],
          minimum_years_experience: null,
          education_level: null,
          duration_days: 30,
        },
        { timeout: 45000 }
      )
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

  it('hides the status select and shows save button in edit mode', () => {
    render(<JobForm companyId="company-1" job={mockJob} />)

    expect(
      screen.queryByLabelText('Trạng thái'),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Lưu thay đổi/i }),
    ).toBeInTheDocument()
  })

  it('submits an update via PATCH to the recruiter job endpoint', async () => {
    const updated: Job = { ...mockJob, title: 'Staff Frontend Engineer' }
    const mockedPatch = vi.mocked(apiClient.patch)
    mockedPatch.mockResolvedValue(updated as never)

    render(<JobForm companyId="company-1" job={mockJob} />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Staff Frontend Engineer' },
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Lưu thay đổi/i }),
    )

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith('/jobs/mine/job-1', {
        title: 'Staff Frontend Engineer',
        description: 'Build modern web applications with React.',
        job_type: 'full_time',
        workplace_type: 'remote',
        location: 'Ho Chi Minh City',
        required_skills: [],
        preferred_skills: [],
        minimum_years_experience: null,
        education_level: null,
      })
      expect(
        screen.getByText('Cập nhật tin tuyển dụng thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('calls onSaved with the updated job', async () => {
    const updated: Job = { ...mockJob, title: 'Staff Frontend Engineer' }
    const mockedPatch = vi.mocked(apiClient.patch)
    mockedPatch.mockResolvedValue(updated as never)
    const onSaved = vi.fn()

    render(<JobForm companyId="company-1" job={mockJob} onSaved={onSaved} />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Staff Frontend Engineer' },
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Lưu thay đổi/i }),
    )

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(updated)
    })
  })

  it('allows selecting preset duration on creation', async () => {
    mockedPost.mockResolvedValue(mockJob as never)

    render(<JobForm companyId="company-1" />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Frontend Lead' },
    })
    fireEvent.change(screen.getByLabelText('Mô tả công việc'), {
      target: { value: 'Lead the frontend team' },
    })

    fireEvent.click(screen.getByRole('button', { name: '14 ngày' }))

    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/jobs',
        expect.objectContaining({
          duration_days: 14,
        }),
        { timeout: 45000 }
      )
    })
  })

  it('hydrates all 4 fields including 0 minimum experience', () => {
    const jobWithAllFields: Job = {
      ...mockJob,
      required_skills: ['Go', 'Kubernetes'],
      preferred_skills: ['gRPC', 'Terraform'],
      minimum_years_experience: 0,
      education_level: 'Bachelor',
    }

    render(<JobForm companyId="company-1" job={jobWithAllFields} />)

    expect(screen.getByLabelText('Kỹ năng bắt buộc')).toHaveValue('Go, Kubernetes')
    expect(screen.getByLabelText('Kỹ năng ưu tiên')).toHaveValue('gRPC, Terraform')
    expect(screen.getByLabelText('Kinh nghiệm tối thiểu (năm)')).toHaveValue(0)
    expect(screen.getByLabelText('Yêu cầu học vấn')).toHaveValue('Bachelor')
  })

  it('omits duration_days on normal edit of published job without extension selection', async () => {
    const publishedJob: Job = {
      ...mockJob,
      status: 'published',
      published_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 30 * 86400 * 1000).toISOString(),
    }
    const mockedPatch = vi.mocked(apiClient.patch)
    mockedPatch.mockResolvedValue(publishedJob as never)

    render(<JobForm companyId="company-1" job={publishedJob} />)

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Updated Title' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Lưu thay đổi/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith(
        '/jobs/mine/job-1',
        expect.not.objectContaining({
          duration_days: expect.anything(),
        })
      )
    })
  })

  it('includes duration_days and previews new expiry when extension is selected', async () => {
    const publishedJob: Job = {
      ...mockJob,
      status: 'published',
      published_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 10 * 86400 * 1000).toISOString(),
    }
    const mockedPatch = vi.mocked(apiClient.patch)
    mockedPatch.mockResolvedValue(publishedJob as never)

    render(<JobForm companyId="company-1" job={publishedJob} />)

    const btn14 = screen.getByRole('button', { name: '+14 ngày' })
    fireEvent.click(btn14)

    expect(screen.getByText(/Hạn mới dự kiến:/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Lưu thay đổi/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith(
        '/jobs/mine/job-1',
        expect.objectContaining({
          duration_days: 14,
        })
      )
    })
  })

  it('disables extension button exceeding 90-day lifetime cap', () => {
    // Job published 80 days ago with expiry in 5 days (total 85 days)
    // +14 days would exceed 90 days lifetime
    const now = Date.now()
    const pubDate = new Date(now - 80 * 86400 * 1000)
    const expDate = new Date(now + 5 * 86400 * 1000)

    const nearCapJob: Job = {
      ...mockJob,
      status: 'published',
      published_at: pubDate.toISOString(),
      expires_at: expDate.toISOString(),
    }

    render(<JobForm companyId="company-1" job={nearCapJob} />)

    const btn14 = screen.getByRole('button', { name: '+14 ngày' })
    const btn30 = screen.getByRole('button', { name: '+30 ngày' })

    expect(btn14).toBeDisabled()
    expect(btn30).toBeDisabled()
    expect(
      screen.getByText(/Thời hạn đăng tối đa là 90 ngày kể từ ngày đăng tin lần đầu/i)
    ).toBeInTheDocument()
  })

  it('shows expired notice and no extension buttons when published job is expired', () => {
    const expiredJob: Job = {
      ...mockJob,
      status: 'expired',
      expires_at: new Date(Date.now() - 86400 * 1000).toISOString(),
    }

    render(<JobForm companyId="company-1" job={expiredJob} />)

    expect(
      screen.getByText('Tin tuyển dụng này đã hết hạn, không thể gia hạn.')
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+14 ngày' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+30 ngày' })).not.toBeInTheDocument()
  })
})