import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApplicationMatchExplanation } from './ApplicationMatchExplanation'
import * as applicationsApi from '@/api/applications'
import type {
  ApplicationMatchExplanationResponse,
  ExperienceEvaluation,
  SkillEvaluation,
} from '@/types/ai'

vi.mock('@/api/applications', () => ({
  getApplicationMatchExplanation: vi.fn(),
  refreshApplicationMatchExplanation: vi.fn(),
}))

const mockGet = vi.mocked(applicationsApi.getApplicationMatchExplanation)
const mockRefresh = vi.mocked(
  applicationsApi.refreshApplicationMatchExplanation,
)

function makeExplanation(
  overrides: Partial<ApplicationMatchExplanationResponse> = {},
): ApplicationMatchExplanationResponse {
  return {
    application_id: 'app-1',
    overall_score: 85,
    score_breakdown: {
      overall_score: 85,
      cosine_similarity: 0.9,
      skill_coverage_score: 0.8,
      preferred_skill_coverage_score: 0.5,
      experience_match_score: 0.7,
      education_score: 1,
      project_score: 0.25,
    },
    summary: 'Ứng viên phù hợp cho vị trí backend.',
    summary_source: 'deterministic',
    skill_evaluations: [],
    experience_evaluations: [],
    key_strengths: [],
    areas_for_inquiry: [],
    evidence: [],
    data_limitations: [],
    confidence: null,
    model_version: null,
    generated_at: '2026-01-20T07:00:00Z',
    cache_state: 'not_cached',
    ...overrides,
  }
}

const sampleSkill: SkillEvaluation = {
  skill_name: 'FastAPI',
  requirement_type: 'required',
  status: 'matched_evidenced',
  explanation: 'FastAPI là kỹ năng bắt buộc và có dẫn chứng.',
  evidence: [],
}

const sampleExperience: ExperienceEvaluation = {
  role_title: 'Senior Engineer',
  company: 'Acme Corp',
  duration: '2020 — Present',
  relevance: 'relevant_skills',
  explanation: 'Vai trò có sử dụng kỹ năng yêu cầu.',
  evidence: [],
}

function httpError(
  status: number,
  options?: { headers?: Record<string, string>; data?: unknown },
): Error {
  const error = new Error(`HTTP ${status}`)
  Object.assign(error, {
    response: {
      status,
      headers: options?.headers ?? {},
      data: options?.data,
    },
  })
  return error
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

function renderExplanation(applicationId = 'app-1') {
  return render(<ApplicationMatchExplanation applicationId={applicationId} />)
}

function refreshButton() {
  return screen.getByRole('button', { name: /phân tích AI/i })
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ApplicationMatchExplanation', () => {
  it('shows a loading state then renders the fetched explanation', async () => {
    const pending = deferred<ApplicationMatchExplanationResponse>()
    mockGet.mockReturnValueOnce(pending.promise)

    renderExplanation()

    expect(screen.getByText('Đang tải phân tích đối sánh...')).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith('app-1')

    await act(async () => {
      pending.resolve(makeExplanation())
      await pending.promise
    })
    await settle()

    expect(
      screen.getByText('Ứng viên phù hợp cho vị trí backend.'),
    ).toBeInTheDocument()
  })

  it('renders a deterministic summary with the automatic source badge', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    renderExplanation()
    await settle()

    expect(screen.getByText('Tóm tắt tự động')).toBeInTheDocument()
    expect(screen.queryByText('Tóm tắt do AI tạo')).not.toBeInTheDocument()
  })

  it('renders an AI-generated, cached summary with distinct badges', async () => {
    mockGet.mockResolvedValue(
      makeExplanation({
        summary_source: 'ai_generated',
        cache_state: 'cached',
        model_version: 'gemini-2.5-flash',
      }),
    )
    renderExplanation()
    await settle()

    expect(screen.getByText('Tóm tắt do AI tạo')).toBeInTheDocument()
    expect(screen.getByText('Đã lưu trong bộ nhớ đệm')).toBeInTheDocument()
    expect(screen.getByText('Mô hình: gemini-2.5-flash')).toBeInTheDocument()
    expect(screen.getByText(/Cập nhật lúc/)).toBeInTheDocument()
  })

  it('renders the overall score and the full breakdown with consistent scales', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    renderExplanation()
    await settle()

    expect(
      screen.getByLabelText('Điểm đối sánh tổng thể 85 phần trăm'),
    ).toBeInTheDocument()
    expect(screen.getByText('Độ tương đồng ngữ nghĩa')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('70%')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
  })

  it('composes the skill, experience and inquiry sections', async () => {
    mockGet.mockResolvedValue(
      makeExplanation({
        skill_evaluations: [sampleSkill],
        experience_evaluations: [sampleExperience],
        areas_for_inquiry: ['Hỏi về tối ưu truy vấn SQL'],
      }),
    )
    renderExplanation()
    await settle()

    expect(screen.getByText('Đối soát kỹ năng')).toBeInTheDocument()
    expect(screen.getByText('FastAPI')).toBeInTheDocument()
    expect(screen.getByText('Kinh nghiệm liên quan')).toBeInTheDocument()
    expect(screen.getByText('Senior Engineer · Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Gợi ý câu hỏi phỏng vấn')).toBeInTheDocument()
    expect(screen.getByText('Hỏi về tối ưu truy vấn SQL')).toBeInTheDocument()
  })

  it('handles empty evidence and data limitations gracefully', async () => {
    mockGet.mockResolvedValue(
      makeExplanation({
        evidence: [],
        data_limitations: [],
      }),
    )
    renderExplanation()
    await settle()

    expect(
      screen.queryByText(/Tất cả dẫn chứng từ CV/),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Lưu ý về dữ liệu')).not.toBeInTheDocument()
  })

  it('renders the consolidated evidence and data limitations when present', async () => {
    mockGet.mockResolvedValue(
      makeExplanation({
        evidence: [
          {
            section: 'skills',
            field_name: null,
            item_index: null,
            item_title: null,
            quote: 'FastAPI',
          },
        ],
        data_limitations: ['CV không có chứng chỉ chính thức.'],
      }),
    )
    renderExplanation()
    await settle()

    expect(screen.getByText('Tất cả dẫn chứng từ CV (1)')).toBeInTheDocument()
    expect(screen.getByText('FastAPI')).toBeInTheDocument()
    expect(screen.getByText('Lưu ý về dữ liệu')).toBeInTheDocument()
    expect(
      screen.getByText('CV không có chứng chỉ chính thức.'),
    ).toBeInTheDocument()
  })

  it('shows a GET error with a working manual retry', async () => {
    mockGet
      .mockRejectedValueOnce(httpError(503))
      .mockResolvedValueOnce(makeExplanation())

    renderExplanation()
    await settle()

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Không thể tải phân tích đối sánh',
    )

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))
    await settle()

    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(
      screen.getByText('Ứng viên phù hợp cho vị trí backend.'),
    ).toBeInTheDocument()
  })

  it('updates the view after a successful refresh', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    mockRefresh.mockResolvedValue(
      makeExplanation({
        summary: 'Phân tích AI mới.',
        summary_source: 'ai_generated',
        cache_state: 'not_cached',
      }),
    )

    renderExplanation()
    await settle()

    fireEvent.click(refreshButton())
    await settle()

    expect(mockRefresh).toHaveBeenCalledTimes(1)
    const [calledId, calledKey] = mockRefresh.mock.calls[0]
    expect(calledId).toBe('app-1')
    expect(typeof calledKey).toBe('string')
    expect(calledKey).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    )
    expect(screen.getByText('Phân tích AI mới.')).toBeInTheDocument()
    expect(screen.getByText('Tóm tắt do AI tạo')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Đã cập nhật phân tích AI',
    )
  })

  it('prevents double submissions while refreshing', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    const pending = deferred<ApplicationMatchExplanationResponse>()
    mockRefresh.mockReturnValueOnce(pending.promise)

    renderExplanation()
    await settle()

    const button = refreshButton()
    fireEvent.click(button)

    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button).toHaveTextContent('Đang phân tích...')

    fireEvent.click(button)
    expect(mockRefresh).toHaveBeenCalledTimes(1)

    await act(async () => {
      pending.resolve(
        makeExplanation({ summary: 'Xong.', summary_source: 'ai_generated' }),
      )
      await pending.promise
    })
    await settle()

    expect(mockRefresh).toHaveBeenCalledTimes(1)
  })

  it('handles a 409 conflict with a countdown and no automatic retry', async () => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue(makeExplanation())
    mockRefresh.mockRejectedValueOnce(
      httpError(409, { headers: { 'retry-after': '3' } }),
    )

    const { unmount } = renderExplanation()
    await settle()

    const button = refreshButton()
    fireEvent.click(button)
    await settle()

    expect(screen.getByRole('status')).toHaveTextContent(/đang xử lý/)
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Thử lại sau 3s')

    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(button).toHaveTextContent('Thử lại sau 2s')

    act(() => {
      vi.advanceTimersByTime(1000)
    })
    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(mockRefresh).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('status')).toHaveTextContent('Bạn có thể thử lại')
    expect(button).not.toBeDisabled()

    expect(vi.getTimerCount()).toBe(0)
    unmount()
  })

  it('cleans up the countdown timer on unmount', async () => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue(makeExplanation())
    mockRefresh.mockRejectedValueOnce(
      httpError(409, { headers: { 'retry-after': '10' } }),
    )

    const { unmount } = renderExplanation()
    await settle()

    fireEvent.click(refreshButton())
    await settle()

    expect(vi.getTimerCount()).toBeGreaterThan(0)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('shows a persistent quota warning for 429 without retrying', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    mockRefresh.mockRejectedValueOnce(httpError(429))

    renderExplanation()
    await settle()

    fireEvent.click(refreshButton())
    await settle()

    expect(screen.getByRole('alert')).toHaveTextContent(/hết hạn mức/)
    expect(mockRefresh).toHaveBeenCalledTimes(1)
    expect(
      screen.getByText('Ứng viên phù hợp cho vị trí backend.'),
    ).toBeInTheDocument()
    // Quota is a distinct outcome from a generic conflict.
    expect(screen.queryByText(/đang xử lý/)).not.toBeInTheDocument()
  })

  it('preserves valid data when a refresh fails with 503', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    mockRefresh.mockRejectedValueOnce(httpError(503))

    renderExplanation()
    await settle()

    fireEvent.click(refreshButton())
    await settle()

    expect(screen.getByRole('alert')).toHaveTextContent(
      /Dịch vụ phân tích AI tạm thời không khả dụng/,
    )
    expect(
      screen.getByText('Ứng viên phù hợp cho vị trí backend.'),
    ).toBeInTheDocument()
  })

  it('reuses the idempotency key when retrying an ambiguous failure', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    mockRefresh
      .mockRejectedValueOnce(httpError(503))
      .mockResolvedValueOnce(makeExplanation({ summary: 'Thành công sau đó.' }))

    renderExplanation()
    await settle()

    fireEvent.click(refreshButton())
    await settle()

    fireEvent.click(refreshButton())
    await settle()

    expect(mockRefresh).toHaveBeenCalledTimes(2)
    expect(mockRefresh.mock.calls[1][1]).toBe(mockRefresh.mock.calls[0][1])
    expect(screen.getByText('Thành công sau đó.')).toBeInTheDocument()
  })

  it('uses a new idempotency key for a deliberate new refresh', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    mockRefresh
      .mockResolvedValueOnce(makeExplanation({ summary: 'Lần một.' }))
      .mockResolvedValueOnce(makeExplanation({ summary: 'Lần hai.' }))

    renderExplanation()
    await settle()

    fireEvent.click(refreshButton())
    await settle()
    fireEvent.click(refreshButton())
    await settle()

    expect(mockRefresh).toHaveBeenCalledTimes(2)
    expect(mockRefresh.mock.calls[1][1]).not.toBe(mockRefresh.mock.calls[0][1])
    expect(screen.getByText('Lần hai.')).toBeInTheDocument()
  })

  it('discards a stale GET response after the application changes', async () => {
    const first = deferred<ApplicationMatchExplanationResponse>()
    const second = deferred<ApplicationMatchExplanationResponse>()
    mockGet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const { rerender } = renderExplanation('app-1')
    rerender(<ApplicationMatchExplanation applicationId="app-2" />)

    await act(async () => {
      second.resolve(makeExplanation({ application_id: 'app-2', summary: 'Kết quả app-2.' }))
      await second.promise
    })
    await settle()
    expect(screen.getByText('Kết quả app-2.')).toBeInTheDocument()

    await act(async () => {
      first.resolve(makeExplanation({ application_id: 'app-1', summary: 'Kết quả app-1.' }))
      await first.promise
    })
    await settle()

    expect(screen.queryByText('Kết quả app-1.')).not.toBeInTheDocument()
    expect(screen.getByText('Kết quả app-2.')).toBeInTheDocument()
  })

  it('discards a refresh response after the application changes', async () => {
    mockGet
      .mockResolvedValueOnce(makeExplanation({ summary: 'App-1 ban đầu.' }))
      .mockResolvedValueOnce(makeExplanation({ application_id: 'app-2', summary: 'App-2 ban đầu.' }))
    const pendingRefresh = deferred<ApplicationMatchExplanationResponse>()
    mockRefresh.mockReturnValueOnce(pendingRefresh.promise)

    const { rerender } = renderExplanation('app-1')
    await settle()

    fireEvent.click(refreshButton())
    await settle()

    rerender(<ApplicationMatchExplanation applicationId="app-2" />)
    await settle()
    expect(screen.getByText('App-2 ban đầu.')).toBeInTheDocument()

    await act(async () => {
      pendingRefresh.resolve(makeExplanation({ summary: 'Refresh cũ của app-1.' }))
      await pendingRefresh.promise
    })
    await settle()

    expect(screen.queryByText('Refresh cũ của app-1.')).not.toBeInTheDocument()
    expect(screen.getByText('App-2 ban đầu.')).toBeInTheDocument()
  })

  it('does not update state after unmount', async () => {
    const pending = deferred<ApplicationMatchExplanationResponse>()
    mockGet.mockReturnValueOnce(pending.promise)

    const { unmount } = renderExplanation()
    unmount()

    await act(async () => {
      pending.resolve(makeExplanation())
      await pending.promise
    })

    expect(screen.queryByText('Ứng viên phù hợp cho vị trí backend.')).not.toBeInTheDocument()
  })

  it('handles nullable fields and an invalid timestamp', async () => {
    mockGet.mockResolvedValue(
      makeExplanation({
        model_version: null,
        confidence: null,
        generated_at: 'not-a-date',
      }),
    )
    renderExplanation()
    await settle()

    expect(screen.queryByText(/Cập nhật lúc/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Mô hình:/)).not.toBeInTheDocument()
    expect(
      screen.getByText('Ứng viên phù hợp cho vị trí backend.'),
    ).toBeInTheDocument()
  })

  it('exposes refresh control and alert/status semantics', async () => {
    mockGet.mockResolvedValue(makeExplanation())
    mockRefresh.mockRejectedValueOnce(httpError(429))

    renderExplanation()
    await settle()

    const button = refreshButton()
    expect(button).not.toBeDisabled()

    fireEvent.click(button)
    await settle()

    expect(screen.getByRole('alert')).toHaveTextContent(/hết hạn mức/)
  })
})
