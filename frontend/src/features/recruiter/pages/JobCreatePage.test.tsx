import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { JobCreatePage } from './JobCreatePage'
import apiClient from '@/api/client'
import type { Job } from '@/types/job'
import type { ParsedJob } from '@/features/recruiter/components/AIPredictJDModal'

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

const mockParsedJob: ParsedJob = {
  title: 'Senior Frontend Engineer',
  summary: 'Build modern web applications with React.',
  required_skills: ['React', 'TypeScript'],
  preferred_skills: ['Next.js'],
  minimum_years_experience: 3,
  education_level: 'Bachelor degree',
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

describe('JobCreatePage', () => {
  it('requires recruiter to have a company', () => {
    render(
      <MemoryRouter>
        <JobCreatePage companyId={null} />
      </MemoryRouter>,
    )

    expect(
      screen.getByText(
        /Bạn cần tạo công ty trước khi đăng tin tuyển dụng/i,
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Tạo công ty/i })).toHaveAttribute(
      'href',
      '/recruiter/company',
    )
  })

  it('renders the job form when a company is present', () => {
    render(
      <MemoryRouter>
        <JobCreatePage companyId="company-1" />
      </MemoryRouter>,
    )

    expect(screen.getByText('Thông tin tin tuyển dụng')).toBeInTheDocument()
    expect(screen.getByLabelText('Tiêu đề công việc')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Phân tích JD bằng AI/i }),
    ).toBeInTheDocument()
  })

  it('creates a job successfully', async () => {
    mockedPost.mockResolvedValue(mockJob as never)

    render(
      <MemoryRouter>
        <JobCreatePage companyId="company-1" />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Tiêu đề công việc'), {
      target: { value: 'Senior Frontend Engineer' },
    })
    fireEvent.change(screen.getByLabelText('Mô tả công việc'), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/jobs', {
        company_id: 'company-1',
        title: 'Senior Frontend Engineer',
        description: 'Build modern web applications with React.',
        job_type: 'full_time',
        workplace_type: 'on_site',
        location: null,
        status: 'draft',
      })
      expect(
        screen.getByText('Tạo tin tuyển dụng thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('applies parsed JD from the AI modal into the form', async () => {
    mockedPost.mockResolvedValue(mockParsedJob as never)

    render(
      <MemoryRouter>
        <JobCreatePage companyId="company-1" />
      </MemoryRouter>,
    )

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích JD bằng AI/i }),
    )

    const dialog = screen.getByRole('dialog', {
      name: 'AI phân tích JD',
    })
    expect(dialog).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/Mô tả công việc/), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(
      within(dialog).getByRole('button', { name: /Phân tích JD bằng AI/i }),
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/ai/parse-jd', {
        job_title: '',
        job_description: 'Build modern web applications with React.',
        job_id: null,
      })
    })
  })
})