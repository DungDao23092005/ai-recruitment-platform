import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplicationDetailModal } from './ApplicationDetailModal'
import * as applicationsApi from '@/api/applications'
import apiClient from '@/api/client'
import type { Application, ApplicationDetail } from '@/types/application'

const mockApplication: Application = {
  id: 'app-1',
  candidate_id: '11111111-1111-1111-1111-111111111111',
  job_id: 'job-1',
  status: 'applied',
  created_at: '2026-01-20T00:00:00Z',
  updated_at: '2026-01-20T00:00:00Z',
  candidate: null,
}

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

const mockedGetApplicationDetail = vi.mocked(
  applicationsApi.getApplicationDetail,
)
const mockedPatch = vi.mocked(apiClient.patch)

beforeEach(() => {
  vi.clearAllMocks()
})

function renderModal(props = {}) {
  return render(
    <ApplicationDetailModal
      application={mockApplication}
      onClose={vi.fn()}
      {...props}
    />,
  )
}

describe('ApplicationDetailModal', () => {
  it('shows loading state while fetching', () => {
    mockedGetApplicationDetail.mockReturnValue(new Promise(() => {}))

    renderModal()

    expect(screen.getByText(/Đang tải chi tiết đơn ứng tuyển/)).toBeInTheDocument()
  })

  it('shows error with retry on failure', async () => {
    const error = new Error('Server Error')
    Object.assign(error, { response: { status: 500 } })
    mockedGetApplicationDetail.mockRejectedValueOnce(error)
    mockedGetApplicationDetail.mockResolvedValueOnce(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedGetApplicationDetail).toHaveBeenCalledTimes(2)
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })
  })

  it('renders application info and digital CV sections', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getAllByText('Nguyễn Văn A').length).toBeGreaterThan(0)
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
      expect(screen.getByText('Đã nộp')).toBeInTheDocument()
      expect(screen.getByText('Xây dựng API.')).toBeInTheDocument()
      expect(screen.getByText('Kỹ năng')).toBeInTheDocument()
      expect(screen.getAllByText('Python').length).toBeGreaterThan(0)
      expect(screen.getByText('Kinh nghiệm làm việc')).toBeInTheDocument()
      expect(screen.getByText('Senior Engineer · Acme')).toBeInTheDocument()
      expect(screen.getByText('Học vấn')).toBeInTheDocument()
      expect(screen.getByText('HUST')).toBeInTheDocument()
      expect(screen.getByText('Chứng chỉ')).toBeInTheDocument()
      expect(screen.getByText('AWS SAA')).toBeInTheDocument()
      expect(screen.getByText('Ngoại ngữ')).toBeInTheDocument()
      expect(screen.getByText('English')).toBeInTheDocument()
    })
  })

  it('shows no CV message when resume is null', async () => {
    mockedGetApplicationDetail.mockResolvedValue({
      ...mockDetail,
      resume: null,
    })

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Chưa có hồ sơ CV')).toBeInTheDocument()
    })
  })

  it('shows message when parsed_data is null', async () => {
    mockedGetApplicationDetail.mockResolvedValue({
      ...mockDetail,
      resume: { ...mockDetail.resume!, parsed_data: null },
    })

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('CV chưa có dữ liệu')).toBeInTheDocument()
    })
  })

  it('opens status update modal and refreshes detail on success', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    const updated: Application = { ...mockApplication, status: 'under_review' }
    mockedPatch.mockResolvedValue(updated as never)
    const onStatusChange = vi.fn()

    renderModal({ onStatusChange })

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Cập nhật trạng thái/i }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn ứng tuyển' }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Lưu trạng thái/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith('/applications/app-1/status', {
        status: 'under_review',
      })
    })
  })
})