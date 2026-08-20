import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplicantList } from './ApplicantList'
import * as applicationsApi from '@/api/applications'
import apiClient from '@/api/client'
import type { Application, ApplicationDetail } from '@/types/application'

const mockApplications: Application[] = [
  {
    id: 'app-1',
    candidate_id: '11111111-1111-1111-1111-111111111111',
    job_id: 'job-1',
    status: 'applied',
    created_at: '2026-01-20T00:00:00Z',
    updated_at: '2026-01-20T00:00:00Z',
    candidate: null,
  },
  {
    id: 'app-2',
    candidate_id: '22222222-2222-2222-2222-222222222222',
    job_id: 'job-1',
    status: 'shortlisted',
    created_at: '2026-01-21T00:00:00Z',
    updated_at: '2026-01-22T00:00:00Z',
    candidate: null,
  },
]

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

vi.mock('@/api/applications', () => ({
  getApplicationDetail: vi.fn(),
}))

const mockedPatch = vi.mocked(apiClient.patch)
const mockedGetApplicationDetail = vi.mocked(
  applicationsApi.getApplicationDetail,
)

const mockDetail: ApplicationDetail = {
  id: 'app-1',
  candidate_id: '11111111-1111-1111-1111-111111111111',
  job_id: 'job-1',
  job_title: 'Backend Engineer',
  company_name: 'Acme Corp',
  status: 'applied',
  created_at: '2026-01-20T00:00:00Z',
  updated_at: '2026-01-20T00:00:00Z',
  candidate: {
    id: '11111111-1111-1111-1111-111111111111',
    full_name: 'Nguyễn Văn A',
    title: 'Backend Engineer',
  },
  resume: {
    id: 'res-1',
    candidate_id: '11111111-1111-1111-1111-111111111111',
    title: 'cv.pdf',
    is_primary: true,
    parsed_data: {
      full_name: 'Nguyễn Văn A',
      email: 'a@example.com',
      phone: '0901234567',
      title: 'Backend Engineer',
      summary: 'Xây dựng API.',
      total_years_experience: 5,
      skills: ['Python', 'FastAPI'],
      experiences: [
        {
          company: 'Acme',
          position: 'Senior Engineer',
          start_date: '2020/01',
          end_date: 'Present',
          is_current: true,
          description: 'Led platform team.',
          skills_used: ['Python'],
        },
      ],
      education: [
        {
          institution: 'HUST',
          degree: 'Bachelor',
          field_of_study: 'CS',
          start_year: 2010,
          end_year: 2014,
        },
      ],
      certifications: ['AWS SAA'],
      languages: ['English'],
    },
    created_at: '2026-01-20T00:00:00Z',
    updated_at: '2026-01-20T00:00:00Z',
  },
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ApplicantList', () => {
  it('renders applicant information', () => {
    render(<ApplicantList applications={mockApplications} />)

    expect(
      screen.getByText('Ứng viên 11111111'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Ứng viên 22222222'),
    ).toBeInTheDocument()
  })

  it('renders candidate full name when present', () => {
    const applications: Application[] = [
      {
        ...mockApplications[0],
        candidate: {
          id: '11111111-1111-1111-1111-111111111111',
          full_name: 'Nguyễn Văn A',
          title: 'Backend Engineer',
        },
      },
    ]

    render(<ApplicantList applications={applications} />)

    expect(screen.getByText('Nguyễn Văn A')).toBeInTheDocument()
    expect(
      screen.queryByText('Ứng viên 11111111'),
    ).not.toBeInTheDocument()
  })

  it('falls back to candidate id prefix when full name is null', () => {
    const applications: Application[] = [
      {
        ...mockApplications[0],
        candidate: {
          id: '11111111-1111-1111-1111-111111111111',
          full_name: null,
          title: null,
        },
      },
    ]

    render(<ApplicantList applications={applications} />)

    expect(
      screen.getByText('Ứng viên 11111111'),
    ).toBeInTheDocument()
  })

  it('renders a status badge for each applicant', () => {
    render(<ApplicantList applications={mockApplications} />)

    expect(screen.getByText('Đã nộp')).toBeInTheDocument()
    expect(screen.getByText('Lọt vòng ngắn')).toBeInTheDocument()
  })

  it('renders submitted time when available', () => {
    render(<ApplicantList applications={mockApplications} />)

    const submittedDates = screen.getAllByText(/20 thg 1, 2026|21 thg 1, 2026/)
    expect(submittedDates.length).toBeGreaterThan(0)
  })

  it('renders without crashing when there are no applicants', () => {
    const { container } = render(<ApplicantList applications={[]} />)

    expect(container.firstChild).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('opens the status update modal for an applicant', () => {
    render(<ApplicantList applications={mockApplications} />)

    fireEvent.click(
      screen.getByRole('button', {
        name: /Cập nhật trạng thái cho đơn ứng tuyển app-1/i,
      }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn ứng tuyển' }),
    ).toBeInTheDocument()
  })

  it('opens the application detail modal with the digital CV', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    render(<ApplicantList applications={mockApplications} />)

    fireEvent.click(
      screen.getByRole('button', {
        name: /Xem hồ sơ ứng viên 11111111/i,
      }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Chi tiết đơn ứng tuyển' }),
    ).toBeInTheDocument()

    await waitFor(() => {
      expect(mockedGetApplicationDetail).toHaveBeenCalledWith('app-1')
      expect(screen.getAllByText('Nguyễn Văn A').length).toBeGreaterThan(0)
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
      expect(screen.getByText('Xây dựng API.')).toBeInTheDocument()
      expect(screen.getAllByText('Python').length).toBeGreaterThan(0)
    })
  })

  it('shows no CV message when resume is null', async () => {
    mockedGetApplicationDetail.mockResolvedValue({
      ...mockDetail,
      resume: null,
    })

    render(<ApplicantList applications={mockApplications} />)

    fireEvent.click(
      screen.getByRole('button', {
        name: /Xem hồ sơ ứng viên 11111111/i,
      }),
    )

    await waitFor(() => {
      expect(screen.getByText('Chưa có hồ sơ CV')).toBeInTheDocument()
    })
  })

  it('calls onStatusChange when an application status is updated', async () => {
    const onStatusChange = vi.fn()
    const updated: Application = {
      ...mockApplications[0],
      status: 'under_review',
    }
    mockedPatch.mockResolvedValue(updated as never)

    render(
      <ApplicantList
        applications={mockApplications}
        onStatusChange={onStatusChange}
      />,
    )

    fireEvent.click(
      screen.getByRole('button', {
        name: /Cập nhật trạng thái cho đơn ứng tuyển app-1/i,
      }),
    )

    const statusSelect = screen.getByLabelText('Trạng thái')
    fireEvent.change(statusSelect, { target: { value: 'under_review' } })

    fireEvent.click(screen.getByRole('button', { name: /Lưu trạng thái/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith('/applications/app-1/status', {
        status: 'under_review',
      })
      expect(onStatusChange).toHaveBeenCalledWith(updated)
    })
  })
})