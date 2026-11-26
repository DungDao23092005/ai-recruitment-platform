import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { JobCreatePage } from './JobCreatePage'
import apiClient from '@/api/client'
import type { Company } from '@/types/company'
import type { Job } from '@/types/job'
import type { ParsedJob } from '@/features/recruiter/components/AIPredictJDModal'

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

const mockCompanies: Company[] = [
  {
    id: 'company-1',
    name: 'Acme Corp',
    slug: 'acme-corp',
    tax_code: '123456789',
    size: 'startup',
    created_at: '2026-01-10T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
  },
  {
    id: 'company-2',
    name: 'Beta Inc',
    slug: 'beta-inc',
    tax_code: '987654321',
    size: 'sme',
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
]

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

const workspaceMocks = vi.hoisted(() => ({
  selectedCompanyId: null as string | null,
  selectWorkspace: vi.fn(),
  refreshWorkspaces: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    selectedCompanyId: workspaceMocks.selectedCompanyId,
    selectWorkspace: workspaceMocks.selectWorkspace,
    refreshWorkspaces: workspaceMocks.refreshWorkspaces,
    workspaces: [],
    selectedWorkspace: null,
    isLoading: false,
    error: null,
  }),
}))

const mockedGet = vi.mocked(apiClient.get)
const mockedPost = vi.mocked(apiClient.post)

beforeEach(() => {
  vi.clearAllMocks()
  workspaceMocks.selectedCompanyId = null
})

describe('JobCreatePage', () => {
  it('shows the empty state when the recruiter has no company', async () => {
    mockedGet.mockResolvedValue([] as never)

    render(
      <MemoryRouter>
        <JobCreatePage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith('/companies')
      expect(
        screen.getByText(/Bạn cần tạo công ty trước khi đăng tin tuyển dụng/i),
      ).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /Tạo công ty/i })).toHaveAttribute(
      'href',
      '/recruiter/company',
    )
  })

  it('fetches and displays the recruiter company when opening the page', async () => {
    mockedGet.mockResolvedValue([mockCompanies[0]] as never)

    render(
      <MemoryRouter>
        <JobCreatePage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith('/companies')
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
      expect(screen.getByText('Thông tin tin tuyển dụng')).toBeInTheDocument()
      expect(screen.getByLabelText('Tiêu đề công việc')).toBeInTheDocument()
    })
  })

  it('shows a company selector when the recruiter has multiple companies', async () => {
    mockedGet.mockResolvedValue(mockCompanies as never)

    render(
      <MemoryRouter>
        <JobCreatePage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Chọn công ty')).toBeInTheDocument()
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
      expect(screen.getByText('Beta Inc')).toBeInTheDocument()
    })
    expect(screen.queryByLabelText('Tiêu đề công việc')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Beta Inc'))

    await waitFor(() => {
      expect(screen.getByLabelText('Tiêu đề công việc')).toBeInTheDocument()
    })
  })

  it('shows a friendly error and recovers on retry', async () => {
    const error = new Error('Network Error')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Không thể tải công ty' } },
    })
    mockedGet.mockRejectedValueOnce(error)

    render(
      <MemoryRouter>
        <JobCreatePage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Không thể tải công ty',
      )
    })

    mockedGet.mockResolvedValueOnce([mockCompanies[0]] as never)
    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
      expect(screen.getByLabelText('Tiêu đề công việc')).toBeInTheDocument()
    })
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
    expect(mockedGet).not.toHaveBeenCalled()
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
      expect(mockedPost).toHaveBeenCalledWith(
        '/jobs',
        {
          company_id: 'company-1',
          title: 'Senior Frontend Engineer',
          description: 'Build modern web applications with React.',
          job_type: 'full_time',
          workplace_type: 'on_site',
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

  it('applies parsed JD from the AI modal into the form and submits with required skills', async () => {
    const parsedJobResponse: ParsedJob = {
      title: 'Senior Frontend Engineer',
      summary: 'Build modern web applications with React.',
      required_skills: ['React', 'TypeScript'],
      preferred_skills: ['Next.js'],
      minimum_years_experience: 3,
      education_level: 'Bachelor degree',
    }

    mockedPost
      .mockResolvedValueOnce(parsedJobResponse as never) // /ai/parse-jd
      .mockResolvedValueOnce(mockJob as never) // /jobs

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

    fireEvent.click(
      within(dialog).getByRole('button', { name: /Áp dụng vào tin tuyển dụng/i }),
    )

    await waitFor(() => {
      expect(screen.getByLabelText('Tiêu đề công việc')).toHaveValue('Senior Frontend Engineer')
      expect(screen.getByLabelText('Mô tả công việc')).toHaveValue('Build modern web applications with React.')
      expect(screen.getByLabelText('Kỹ năng bắt buộc')).toHaveValue('React, TypeScript')
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
          workplace_type: 'on_site',
          location: null,
          status: 'draft',
          required_skills: ['React', 'TypeScript'],
          preferred_skills: ['Next.js'],
          minimum_years_experience: 3,
          education_level: 'Bachelor degree',
          duration_days: 30,
        },
        { timeout: 45000 }
      )
      expect(
        screen.getByText('Tạo tin tuyển dụng thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('reapplies AI parsed result with same title but different required skills', async () => {
    const firstParsed: ParsedJob = {
      title: 'Software Engineer',
      summary: 'Frontend role with React.',
      required_skills: ['React', 'TypeScript'],
      preferred_skills: ['Next.js'],
      minimum_years_experience: 3,
      education_level: 'Bachelor degree',
    }

    const secondParsed: ParsedJob = {
      title: 'Software Engineer',
      summary: 'Backend role with Python.',
      required_skills: ['Python', 'FastAPI'],
      preferred_skills: ['Docker'],
      minimum_years_experience: 5,
      education_level: 'Master degree',
    }

    mockedPost
      .mockResolvedValueOnce(firstParsed as never) // first /ai/parse-jd
      .mockResolvedValueOnce(secondParsed as never) // second /ai/parse-jd
      .mockResolvedValueOnce(mockJob as never) // /jobs

    render(
      <MemoryRouter>
        <JobCreatePage companyId="company-1" />
      </MemoryRouter>,
    )

    // First AI parse
    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích JD bằng AI/i }),
    )

    let dialog = screen.getByRole('dialog', { name: 'AI phân tích JD' })
    expect(dialog).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/Mô tả công việc/), {
      target: { value: 'Frontend role with React.' },
    })

    fireEvent.click(
      within(dialog).getByRole('button', { name: /Phân tích JD bằng AI/i }),
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/ai/parse-jd', {
        job_title: '',
        job_description: 'Frontend role with React.',
        job_id: null,
      })
    })

    fireEvent.click(
      within(dialog).getByRole('button', { name: /Áp dụng vào tin tuyển dụng/i }),
    )

    await waitFor(() => {
      expect(screen.getByLabelText('Tiêu đề công việc')).toHaveValue('Software Engineer')
      expect(screen.getByLabelText('Mô tả công việc')).toHaveValue('Frontend role with React.')
      expect(screen.getByLabelText('Kỹ năng bắt buộc')).toHaveValue('React, TypeScript')
    })

    // Second AI parse with SAME title but different skills
    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích JD bằng AI/i }),
    )

    dialog = screen.getByRole('dialog', { name: 'AI phân tích JD' })
    expect(dialog).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/Mô tả công việc/), {
      target: { value: 'Backend role with Python.' },
    })

    fireEvent.click(
      within(dialog).getByRole('button', { name: /Phân tích JD bằng AI/i }),
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/ai/parse-jd', {
        job_title: '',
        job_description: 'Backend role with Python.',
        job_id: null,
      })
    })

    fireEvent.click(
      within(dialog).getByRole('button', { name: /Áp dụng vào tin tuyển dụng/i }),
    )

    await waitFor(() => {
      expect(screen.getByLabelText('Tiêu đề công việc')).toHaveValue('Software Engineer')
      expect(screen.getByLabelText('Mô tả công việc')).toHaveValue('Backend role with Python.')
      expect(screen.getByLabelText('Kỹ năng bắt buộc')).toHaveValue('Python, FastAPI')
    })

    // Submit second result
    fireEvent.click(screen.getByRole('button', { name: /Tạo tin tuyển dụng/i }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/jobs',
        {
          company_id: 'company-1',
          title: 'Software Engineer',
          description: 'Backend role with Python.',
          job_type: 'full_time',
          workplace_type: 'on_site',
          location: null,
          status: 'draft',
          required_skills: ['Python', 'FastAPI'],
          preferred_skills: ['Docker'],
          minimum_years_experience: 5,
          education_level: 'Master degree',
          duration_days: 30,
        },
        { timeout: 45000 }
      )
      expect(
        screen.getByText('Tạo tin tuyển dụng thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('opens AI modal when contextual AI button in form is clicked', async () => {
    render(
      <MemoryRouter>
        <JobCreatePage companyId="company-1" />
      </MemoryRouter>,
    )

    const contextualAiButton = screen.getByRole('button', {
      name: /Bóc tách kỹ năng bằng AI/i,
    })
    expect(contextualAiButton).toBeInTheDocument()
    fireEvent.click(contextualAiButton)

    expect(
      screen.getByRole('dialog', { name: 'AI phân tích JD' }),
    ).toBeInTheDocument()
  })

  describe('Contextual Job Creation & Precedence (PO2 & PO3)', () => {
    it('defaults to active authorized workspace without showing selector on direct navigation', async () => {
      workspaceMocks.selectedCompanyId = 'company-1'
      mockedGet.mockResolvedValue(mockCompanies as never)

      render(
        <MemoryRouter initialEntries={['/recruiter/jobs/new']}>
          <JobCreatePage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Acme Corp')).toBeInTheDocument()
        expect(screen.getByLabelText('Tiêu đề công việc')).toBeInTheDocument()
      })
      // Selector prompt is not shown
      expect(screen.queryByText('Chọn công ty')).not.toBeInTheDocument()
      // "Đổi công ty" button is available
      expect(
        screen.getByRole('button', { name: /Đổi công ty/i }),
      ).toBeInTheDocument()
    })

    it('preselects company from valid query param and synchronizes workspace', async () => {
      workspaceMocks.selectedCompanyId = 'company-1'
      mockedGet.mockResolvedValue(mockCompanies as never)

      render(
        <MemoryRouter initialEntries={['/recruiter/jobs/new?company_id=company-2']}>
          <JobCreatePage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Beta Inc')).toBeInTheDocument()
        expect(screen.getByLabelText('Tiêu đề công việc')).toBeInTheDocument()
      })
      expect(screen.queryByText('Chọn công ty')).not.toBeInTheDocument()
      expect(workspaceMocks.selectWorkspace).toHaveBeenCalledWith('company-2')
    })

    it('safely rejects unauthorized query parameter and falls back to active workspace', async () => {
      workspaceMocks.selectedCompanyId = 'company-1'
      mockedGet.mockResolvedValue(mockCompanies as never)

      render(
        <MemoryRouter initialEntries={['/recruiter/jobs/new?company_id=unauthorized-company-id']}>
          <JobCreatePage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        // Falls back to active workspace Acme Corp
        expect(screen.getByText('Acme Corp')).toBeInTheDocument()
        expect(screen.getByLabelText('Tiêu đề công việc')).toBeInTheDocument()
      })
      expect(screen.queryByText('unauthorized-company-id')).not.toBeInTheDocument()
    })

    it('allows changing company via "Đổi công ty" and shows selector', async () => {
      workspaceMocks.selectedCompanyId = 'company-1'
      mockedGet.mockResolvedValue(mockCompanies as never)

      render(
        <MemoryRouter initialEntries={['/recruiter/jobs/new']}>
          <JobCreatePage />
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Acme Corp')).toBeInTheDocument()
      })

      const changeBtn = screen.getByRole('button', { name: /Đổi công ty/i })
      fireEvent.click(changeBtn)

      await waitFor(() => {
        expect(screen.getByText('Chọn công ty')).toBeInTheDocument()
        expect(screen.getByText('Beta Inc')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Beta Inc'))

      await waitFor(() => {
        expect(screen.getByText('Beta Inc')).toBeInTheDocument()
        expect(screen.getByLabelText('Tiêu đề công việc')).toBeInTheDocument()
      })
      expect(workspaceMocks.selectWorkspace).toHaveBeenCalledWith('company-2')
    })
  })
})
