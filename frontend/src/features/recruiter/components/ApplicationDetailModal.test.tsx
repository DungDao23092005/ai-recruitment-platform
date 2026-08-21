import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplicationDetailModal } from './ApplicationDetailModal'
import * as applicationsApi from '@/api/applications'
import * as aiApi from '@/api/ai'
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
  parsed_job: {
    title: 'Backend Engineer',
    summary: 'Build robust APIs',
    required_skills: ['Python', 'FastAPI'],
    preferred_skills: [],
    minimum_years_experience: 3,
    education_level: null,
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
  getApplicationMatch: vi.fn(),
}))

vi.mock('@/api/ai', () => ({
  explainMatch: vi.fn(),
}))

const mockedGetApplicationDetail = vi.mocked(
  applicationsApi.getApplicationDetail,
)
const mockedGetApplicationMatch = vi.mocked(
  applicationsApi.getApplicationMatch,
)
const mockedExplainMatch = vi.mocked(aiApi.explainMatch)
const mockedPatch = vi.mocked(apiClient.patch)

const mockMatchResult = {
  overall_score: 85,
  cosine_similarity: 0.9,
  skill_coverage_score: 0.5,
  experience_match_score: 1,
  matching_skills: ['Python', 'FastAPI'],
  skill_gap: ['Docker'],
  match_reasons: ['✓ Matching skills: Python'],
}

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

  it('renders the AI Match section with a Phân tích AI button', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    ).toBeInTheDocument()
  })

  it('does not call the match endpoint until the button is clicked', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetApplicationMatch.mockResolvedValue(mockMatchResult)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })
    expect(mockedGetApplicationMatch).not.toHaveBeenCalled()

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    )

    await waitFor(() => {
      expect(mockedGetApplicationMatch).toHaveBeenCalledWith('app-1')
    })
  })

  it('shows loading state while analyzing', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetApplicationMatch.mockReturnValue(new Promise(() => {}))

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    )

    expect(screen.getByText(/Đang phân tích mức độ phù hợp/)).toBeInTheDocument()
  })

  it('renders the match score card on success', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetApplicationMatch.mockResolvedValue(mockMatchResult)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Điểm đối sánh')).toBeInTheDocument()
    })
    expect(screen.getByText('85%')).toBeInTheDocument()
    expect(screen.getByText('Rất phù hợp')).toBeInTheDocument()
  })

  it('renders matched skills and skill gaps', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetApplicationMatch.mockResolvedValue(mockMatchResult)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Điểm đối sánh')).toBeInTheDocument()
    })
    expect(screen.getByText('Kỹ năng khớp')).toBeInTheDocument()
    expect(screen.getByText('Khoảng cách kỹ năng')).toBeInTheDocument()
    expect(screen.getAllByText('Python').length).toBeGreaterThan(0)
    expect(screen.getByText('Docker')).toBeInTheDocument()
  })

  it('shows error with retry when the match endpoint fails', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    const error = new Error('Server Error')
    Object.assign(error, { response: { status: 502 } })
    mockedGetApplicationMatch.mockRejectedValueOnce(error)
    mockedGetApplicationMatch.mockResolvedValueOnce(mockMatchResult)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedGetApplicationMatch).toHaveBeenCalledTimes(2)
      expect(screen.getByText('Điểm đối sánh')).toBeInTheDocument()
    })
  })

  it('shows an empty state when the candidate has no parsed resume data', async () => {
    mockedGetApplicationDetail.mockResolvedValue({
      ...mockDetail,
      resume: { ...mockDetail.resume!, parsed_data: null },
    })

    renderModal()

    await waitFor(() => {
      expect(
        screen.getByText('Chưa có dữ liệu CV để phân tích'),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('button', { name: /Phân tích AI/i }),
    ).not.toBeInTheDocument()
    expect(mockedGetApplicationMatch).not.toHaveBeenCalled()
  })

  it('does not call Gemini until Xem giải thích AI is clicked', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetApplicationMatch.mockResolvedValue(mockMatchResult)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Điểm đối sánh')).toBeInTheDocument()
    })
    expect(mockedExplainMatch).not.toHaveBeenCalled()

    fireEvent.click(
      screen.getByRole('button', { name: /Xem giải thích AI/i }),
    )

    await waitFor(() => {
      expect(mockedExplainMatch).toHaveBeenCalledWith({
        match_result: mockMatchResult,
        candidate: mockDetail.resume?.parsed_data,
        job: mockDetail.parsed_job,
      })
    })
  })

  it('opens the explanation modal with the grounded job data', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetApplicationMatch.mockResolvedValue(mockMatchResult)
    mockedExplainMatch.mockResolvedValue({
      summary: 'Ứng viên phù hợp tốt.',
      strengths: ['Python'],
      skill_gaps: ['Docker'],
      experience_analysis: 'Đủ kinh nghiệm.',
      recommendation: 'Nên phỏng vấn.',
    })

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Điểm đối sánh')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Xem giải thích AI/i }),
    )

    expect(
      screen.getByRole('dialog', {
        name: 'Giải Thích Chi Tiết Độ Phù Hợp Bằng AI',
      }),
    ).toBeInTheDocument()

    await waitFor(() => {
      expect(
        screen.getByText('Ứng viên phù hợp tốt.'),
      ).toBeInTheDocument()
    })
  })

  it('shows an error inside the explanation modal with retry', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetApplicationMatch.mockResolvedValue(mockMatchResult)
    const error = new Error('AI unavailable')
    Object.assign(error, { response: { status: 502 } })
    mockedExplainMatch.mockRejectedValueOnce(error)
    mockedExplainMatch.mockResolvedValueOnce({
      summary: 'OK',
      strengths: [],
      skill_gaps: [],
      experience_analysis: '',
      recommendation: '',
    })

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('AI Match')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Điểm đối sánh')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Xem giải thích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })
})