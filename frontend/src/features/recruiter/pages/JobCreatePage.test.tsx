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
        /Bạn cần tạo company trước khi đăng tin tuyển dụng/i,
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Create a company/i })).toHaveAttribute(
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

    expect(screen.getByText('Job details')).toBeInTheDocument()
    expect(screen.getByLabelText('Job title')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
    ).toBeInTheDocument()
  })

  it('creates a job successfully', async () => {
    mockedPost.mockResolvedValue(mockJob as never)

    render(
      <MemoryRouter>
        <JobCreatePage companyId="company-1" />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Job title'), {
      target: { value: 'Senior Frontend Engineer' },
    })
    fireEvent.change(screen.getByLabelText('Description'), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Create job/i }))

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
        screen.getByText('Job created successfully.'),
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
      screen.getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
    )

    const dialog = screen.getByRole('dialog', {
      name: 'AI job description parser',
    })
    expect(dialog).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/Raw job description/i), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(
      within(dialog).getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
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