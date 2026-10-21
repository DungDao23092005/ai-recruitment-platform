import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { ApplicationDetailModal } from './ApplicationDetailModal'
import * as applicationsApi from '@/api/applications'
import * as aiApi from '@/api/ai'
import apiClient from '@/api/client'
import type { Application, ApplicationDetail } from '@/types/application'
import type { ApplicationMatchExplanationResponse } from '@/types/ai'

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
  interviews: [],
}

const mockApplication2: Application = {
  ...mockApplication,
  id: 'app-2',
  candidate_id: '22222222-2222-2222-2222-222222222222',
}

const mockDetail2: ApplicationDetail = {
  ...mockDetail,
  id: 'app-2',
  candidate_id: '22222222-2222-2222-2222-222222222222',
  job_title: 'Frontend Engineer',
  company_name: 'Beta Inc',
  candidate: {
    id: '22222222-2222-2222-2222-222222222222',
    full_name: 'Trần Thị B',
    title: 'Frontend Engineer',
  },
}

function makeExplanation(
  overrides: Partial<ApplicationMatchExplanationResponse> = {},
): ApplicationMatchExplanationResponse {
  return {
    application_id: 'app-1',
    overall_score: 78,
    score_breakdown: {
      overall_score: 78,
      cosine_similarity: 0.82,
      skill_coverage_score: 0.75,
      preferred_skill_coverage_score: 0.5,
      experience_match_score: 0.9,
      education_score: 1,
      project_score: 0.4,
    },
    summary: 'Tóm tắt đối sánh cho ứng viên.',
    summary_source: 'deterministic',
    skill_evaluations: [],
    experience_evaluations: [],
    key_strengths: [],
    areas_for_inquiry: [],
    evidence: [],
    data_limitations: [],
    confidence: null,
    model_version: null,
    generated_at: '2026-01-20T00:00:00Z',
    cache_state: 'not_cached',
    ...overrides,
  }
}

function httpError(status: number, headers: Record<string, string> = {}) {
  const error = new Error(`HTTP ${status}`)
  Object.assign(error, { response: { status, headers, data: {} } })
  return error
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
  getApplicationMatchExplanation: vi.fn(),
  refreshApplicationMatchExplanation: vi.fn(),
  listApplicationNotes: vi.fn(),
  createApplicationNote: vi.fn(),
  updateApplicationNote: vi.fn(),
  deleteApplicationNote: vi.fn(),
  listApplicationEvaluations: vi.fn(),
  listApplicationActivities: vi.fn(),
}))

vi.mock('@/api/ai', () => ({
  explainMatch: vi.fn(),
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    currentUser: {
      id: 'user-1',
      email: 'r@example.com',
      role: 'recruiter',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    token: 'token',
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshCurrentUser: vi.fn(),
  })),
}))

const mockedGetApplicationDetail = vi.mocked(
  applicationsApi.getApplicationDetail,
)
const mockedGetApplicationMatch = vi.mocked(applicationsApi.getApplicationMatch)
const mockedGetMatchExplanation = vi.mocked(
  applicationsApi.getApplicationMatchExplanation,
)
const mockedRefreshMatchExplanation = vi.mocked(
  applicationsApi.refreshApplicationMatchExplanation,
)
const mockedListNotes = vi.mocked(applicationsApi.listApplicationNotes)
const mockedListActivities = vi.mocked(
  applicationsApi.listApplicationActivities,
)
const mockedExplainMatch = vi.mocked(aiApi.explainMatch)
const mockedPatch = vi.mocked(apiClient.patch)

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

beforeEach(() => {
  vi.clearAllMocks()
  mockedGetApplicationDetail.mockReset()
  mockedGetApplicationMatch.mockReset()
  mockedGetMatchExplanation.mockReset()
  mockedRefreshMatchExplanation.mockReset()
  mockedListNotes.mockReset()
  mockedListActivities.mockReset()
  mockedExplainMatch.mockReset()

  mockedGetMatchExplanation.mockResolvedValue(makeExplanation())
  mockedListNotes.mockResolvedValue([])
  mockedListActivities.mockResolvedValue([])
})

function renderModal(props: Partial<{
  application: Application
  onClose: () => void
  onStatusChange: (updated: Application) => void
}> = {}) {
  return render(
    <MemoryRouter>
      <ApplicationDetailModal
        application={mockApplication}
        onClose={vi.fn()}
        {...props}
      />
    </MemoryRouter>
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
    expect(mockedGetMatchExplanation).not.toHaveBeenCalled()
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
    expect(mockedGetMatchExplanation).not.toHaveBeenCalled()
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

    await waitFor(() => {
      expect(
        screen.queryByRole('dialog', {
          name: 'Cập nhật trạng thái đơn ứng tuyển',
        }),
      ).not.toBeInTheDocument()
    })
    expect(screen.getByText('Đang xem xét')).toBeInTheDocument()
    expect(onStatusChange).toHaveBeenCalledWith(updated)
  })

  it('opens the status dialog immediately without a parent callback', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })

    const trigger = screen.getByRole('button', {
      name: /Cập nhật trạng thái/i,
    })
    expect(trigger).toBeEnabled()

    fireEvent.click(trigger)

    expect(
      screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn ứng tuyển' }),
    ).toBeInTheDocument()
    expect(mockedPatch).not.toHaveBeenCalled()
  })

  it('renders the status dialog outside the detail dialog and keeps the detail open when its backdrop is clicked', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })

    const detailDialog = screen.getByRole('dialog', {
      name: 'Chi tiết đơn ứng tuyển',
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Cập nhật trạng thái/i }),
    )

    const statusDialog = screen.getByRole('dialog', {
      name: 'Cập nhật trạng thái đơn ứng tuyển',
    })
    const statusBackdrop = statusDialog.firstElementChild

    expect(detailDialog).not.toContainElement(statusDialog)
    expect(statusDialog).toHaveClass('fixed', 'inset-0', 'z-50')
    expect(statusBackdrop).not.toBeNull()
    expect(statusBackdrop).toHaveClass('absolute', 'inset-0')

    fireEvent.click(statusBackdrop as HTMLElement)

    expect(statusDialog).not.toBeInTheDocument()
    expect(detailDialog).toBeInTheDocument()
  })

  it('shows a localized 5xx error and retries the status update successfully', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    const updated: Application = { ...mockApplication, status: 'under_review' }
    mockedPatch
      .mockRejectedValueOnce({ response: { status: 500 } })
      .mockResolvedValueOnce(updated as never)
    const onStatusChange = vi.fn()

    renderModal({ onStatusChange })

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Cập nhật trạng thái/i }),
    )
    fireEvent.click(screen.getByRole('button', { name: /Lưu trạng thái/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Hệ thống đang gặp sự cố khi xử lý yêu cầu. Vui lòng thử lại sau.',
      )
    })

    const statusDialog = screen.getByRole('dialog', {
      name: 'Cập nhật trạng thái đơn ứng tuyển',
    })
    const retryButton = screen.getByRole('button', {
      name: /Lưu trạng thái/i,
    })
    expect(statusDialog).toBeInTheDocument()
    expect(retryButton).toBeEnabled()

    fireEvent.click(retryButton)

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledTimes(2)
      expect(
        screen.queryByRole('dialog', {
          name: 'Cập nhật trạng thái đơn ứng tuyển',
        }),
      ).not.toBeInTheDocument()
      expect(onStatusChange).toHaveBeenCalledWith(updated)
    })
    expect(screen.getByText('Đang xem xét')).toBeInTheDocument()
  })

  it('renders the canonical match explanation in the profile tab', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Đối sánh với công việc')).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(
        screen.getByText('Tóm tắt đối sánh cho ứng viên.'),
      ).toBeInTheDocument()
    })

    expect(mockedGetMatchExplanation).toHaveBeenCalledTimes(1)
    expect(mockedGetMatchExplanation).toHaveBeenCalledWith('app-1')
  })

  it('does not activate the legacy explain-match flow', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(
        screen.getByText('Tóm tắt đối sánh cho ứng viên.'),
      ).toBeInTheDocument()
    })

    expect(screen.queryByText('AI Match')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Xem giải thích AI/i }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('dialog', {
        name: /Giải Thích Chi Tiết Độ Phù Hợp Bằng AI/i,
      }),
    ).not.toBeInTheDocument()
    expect(mockedExplainMatch).not.toHaveBeenCalled()
    expect(mockedGetApplicationMatch).not.toHaveBeenCalled()
  })

  it('does not call the canonical GET until the detail has loaded', async () => {
    mockedGetApplicationDetail.mockReturnValue(new Promise(() => {}))

    renderModal()

    expect(screen.getByText(/Đang tải chi tiết đơn ứng tuyển/)).toBeInTheDocument()
    expect(mockedGetMatchExplanation).not.toHaveBeenCalled()
  })

  it('refreshes through the canonical POST endpoint with an idempotency key', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedRefreshMatchExplanation.mockResolvedValueOnce(
      makeExplanation({
        summary: 'Phân tích AI mới.',
        summary_source: 'ai_generated',
      }),
    )

    renderModal()

    await waitFor(() => {
      expect(
        screen.getByText('Tóm tắt đối sánh cho ứng viên.'),
      ).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Tạo phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Phân tích AI mới.')).toBeInTheDocument()
    })

    expect(mockedRefreshMatchExplanation).toHaveBeenCalledTimes(1)
    const [applicationId, idempotencyKey] =
      mockedRefreshMatchExplanation.mock.calls[0]
    expect(applicationId).toBe('app-1')
    expect(typeof idempotencyKey).toBe('string')
    expect(idempotencyKey).toMatch(UUID_PATTERN)
    expect(mockedExplainMatch).not.toHaveBeenCalled()
    expect(mockedGetApplicationMatch).not.toHaveBeenCalled()
  })

  it('keeps the modal shell usable while the explanation is loading', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetMatchExplanation.mockReturnValueOnce(new Promise(() => {}))

    renderModal()

    await waitFor(() => {
      expect(
        screen.getByText('Đang tải phân tích đối sánh...'),
      ).toBeInTheDocument()
    })

    expect(screen.getAllByRole('tab')).toHaveLength(4)
    expect(screen.getByText('Đối sánh với công việc')).toBeInTheDocument()
    expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
  })

  it('shows an error state and retries the explanation', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedGetMatchExplanation.mockRejectedValueOnce(httpError(404))
    mockedGetMatchExplanation.mockResolvedValueOnce(
      makeExplanation({ summary: 'Đã tải lại giải thích.' }),
    )

    renderModal()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        /Không tìm thấy đơn ứng tuyển/,
      )
    })

    // The modal itself remains usable while the explanation failed.
    expect(
      screen.getByRole('tab', { name: /Ghi chú nội bộ/i }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('Đã tải lại giải thích.')).toBeInTheDocument()
    })
    expect(mockedGetMatchExplanation).toHaveBeenCalledTimes(2)
  })

  it('keeps tabs usable during a refresh cooldown', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedRefreshMatchExplanation.mockRejectedValueOnce(
      httpError(409, { 'retry-after': '5' }),
    )

    renderModal()

    await waitFor(() => {
      expect(
        screen.getByText('Tóm tắt đối sánh cho ứng viên.'),
      ).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Tạo phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/đang xử lý/)
    })
    expect(
      screen.getByRole('button', { name: /Thử lại sau 5s/i }),
    ).toBeDisabled()

    fireEvent.click(screen.getByRole('tab', { name: /Ghi chú nội bộ/i }))

    await waitFor(() => {
      expect(mockedListNotes).toHaveBeenCalledWith('app-1', { limit: 50 })
    })
  })

  it('shows a quota warning without discarding the existing explanation', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    mockedRefreshMatchExplanation.mockRejectedValueOnce(httpError(429))

    renderModal()

    await waitFor(() => {
      expect(
        screen.getByText('Tóm tắt đối sánh cho ứng viên.'),
      ).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Tạo phân tích AI/i }),
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/hết hạn mức/)
    })
    expect(
      screen.getByText('Tóm tắt đối sánh cho ứng viên.'),
    ).toBeInTheDocument()
    expect(mockedExplainMatch).not.toHaveBeenCalled()
  })

  it('does not show the previous application explanation after switching', async () => {
    mockedGetApplicationDetail
      .mockResolvedValueOnce(mockDetail)
      .mockResolvedValueOnce(mockDetail2)
    mockedGetMatchExplanation
      .mockResolvedValueOnce(
        makeExplanation({
          application_id: 'app-1',
          summary: 'Giải thích cho ứng viên A.',
        }),
      )
      .mockResolvedValueOnce(
        makeExplanation({
          application_id: 'app-2',
          summary: 'Giải thích cho ứng viên B.',
        }),
      )

    const { rerender } = renderModal()

    await waitFor(() => {
      expect(
        screen.getByText('Giải thích cho ứng viên A.'),
      ).toBeInTheDocument()
    })

    rerender(
      <MemoryRouter>
        <ApplicationDetailModal
          application={mockApplication2}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(
        screen.getByText('Giải thích cho ứng viên B.'),
      ).toBeInTheDocument()
    })

    expect(
      screen.queryByText('Giải thích cho ứng viên A.'),
    ).not.toBeInTheDocument()
    expect(mockedGetMatchExplanation).toHaveBeenLastCalledWith('app-2')
  })

  it('renders the detail tabs and defaults to the profile tab', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })

    expect(screen.getAllByRole('tab')).toHaveLength(4)
    expect(screen.getByRole('tab', { name: /Hồ sơ & Match/i })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByText('Đối sánh với công việc')).toBeInTheDocument()
  })

  it('closes from the footer', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)
    const onClose = vi.fn()

    renderModal({ onClose })

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })

    const closeButtons = screen.getAllByRole('button', { name: 'Đóng' })
    fireEvent.click(closeButtons[closeButtons.length - 1])

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not load internal notes until the notes tab is opened', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })

    expect(mockedListNotes).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('tab', { name: /Ghi chú nội bộ/i }))

    await waitFor(() => {
      expect(mockedListNotes).toHaveBeenCalledWith('app-1', { limit: 50 })
    })
  })

  it('loads activity history only when the activity tab is opened', async () => {
    mockedGetApplicationDetail.mockResolvedValue(mockDetail)

    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Backend Engineer · Acme Corp')).toBeInTheDocument()
    })

    expect(mockedListActivities).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('tab', { name: /Lịch sử hoạt động/i }))

    await waitFor(() => {
      expect(mockedListActivities).toHaveBeenCalledWith('app-1', { limit: 50 })
    })
  })
})
