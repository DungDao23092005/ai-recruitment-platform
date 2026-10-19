import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  CandidateActivityTimeline,
  CANDIDATE_TIMELINE_PAGE_SIZE,
} from './CandidateActivityTimeline'
import * as applicationsApi from '@/api/applications'
import type { CandidateActivity } from '@/types/application'

vi.mock('@/api/applications', () => ({
  getMyApplicationTimeline: vi.fn(),
  getMyApplications: vi.fn(),
  listApplicationActivities: vi.fn(),
  listApplicationNotes: vi.fn(),
  listApplicationEvaluations: vi.fn(),
  getApplicationMatch: vi.fn(),
  updateApplicationStatus: vi.fn(),
}))

const mockedGetTimeline = vi.mocked(applicationsApi.getMyApplicationTimeline)

function activity(overrides: Partial<CandidateActivity>): CandidateActivity {
  return {
    id: 'activity-1',
    action_type: 'status_changed',
    from_status: 'applied',
    to_status: 'under_review',
    created_at: '2026-08-18T10:00:00Z',
    ...overrides,
  }
}

describe('CandidateActivityTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a loading skeleton while fetching', async () => {
    mockedGetTimeline.mockReturnValue(new Promise(() => {}))
    const { container } = render(
      <CandidateActivityTimeline applicationId="app-1" />,
    )

    expect(
      screen.getByText('Đang tải lịch sử hoạt động...'),
    ).toBeInTheDocument()
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(mockedGetTimeline).toHaveBeenCalledWith('app-1', { limit: 20 })
    })
  })

  it('renders candidate-safe activity entries', async () => {
    mockedGetTimeline.mockResolvedValue([
      activity({ id: 'a1' }),
      activity({
        id: 'a2',
        action_type: 'interview_scheduled',
        from_status: null,
        to_status: null,
      }),
    ])

    render(<CandidateActivityTimeline applicationId="app-1" />)

    expect(
      await screen.findByText('Trạng thái đơn ứng tuyển được cập nhật'),
    ).toBeInTheDocument()
    expect(screen.getByText('Lên lịch phỏng vấn')).toBeInTheDocument()
    expect(screen.getByText('Đã nộp')).toBeInTheDocument()
    expect(screen.getByText('Đang xem xét')).toBeInTheDocument()
  })

  it('never renders internal action types verbatim', async () => {
    mockedGetTimeline.mockResolvedValue([
      activity({ id: 'a1', action_type: 'note_added' }),
      activity({ id: 'a2', action_type: 'evaluation_added' }),
    ])

    render(<CandidateActivityTimeline applicationId="app-1" />)

    expect(await screen.findAllByText('Cập nhật đơn ứng tuyển')).toHaveLength(2)
    expect(screen.queryByText(/note_added/)).not.toBeInTheDocument()
    expect(screen.queryByText(/evaluation_added/)).not.toBeInTheDocument()
  })

  it('renders an empty state when there is no activity', async () => {
    mockedGetTimeline.mockResolvedValue([])

    render(<CandidateActivityTimeline applicationId="app-1" />)

    expect(await screen.findByText('Chưa có hoạt động')).toBeInTheDocument()
  })

  it('shows a friendly error and retries', async () => {
    mockedGetTimeline
      .mockRejectedValueOnce(
        Object.assign(new Error('boom'), { response: { status: 500 } }),
      )
      .mockResolvedValueOnce([activity({ id: 'a1' })])

    render(<CandidateActivityTimeline applicationId="app-1" />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    expect(
      await screen.findByText('Trạng thái đơn ứng tuyển được cập nhật'),
    ).toBeInTheDocument()
  })

  it('loads more entries with an increasing page size', async () => {
    const firstPage = Array.from({ length: CANDIDATE_TIMELINE_PAGE_SIZE }).map(
      (_, index) => activity({ id: `a-${index}` }),
    )
    mockedGetTimeline.mockResolvedValueOnce(firstPage)

    render(<CandidateActivityTimeline applicationId="app-1" />)

    await waitFor(() =>
      expect(mockedGetTimeline).toHaveBeenCalledTimes(1),
    )
    fireEvent.click(screen.getByRole('button', { name: /Tải thêm hoạt động/i }))

    await waitFor(() => {
      expect(mockedGetTimeline).toHaveBeenLastCalledWith('app-1', {
        limit: CANDIDATE_TIMELINE_PAGE_SIZE * 2,
      })
    })
  })

  it('hides the load-more button when a short page is returned', async () => {
    mockedGetTimeline.mockResolvedValue([activity({ id: 'a1' })])

    render(<CandidateActivityTimeline applicationId="app-1" />)

    await screen.findByText('Trạng thái đơn ứng tuyển được cập nhật')
    expect(
      screen.queryByRole('button', { name: /Tải thêm hoạt động/i }),
    ).not.toBeInTheDocument()
  })

  it('ignores a stale response when the application changes', async () => {
    const resolvers: Record<string, (value: CandidateActivity[]) => void> = {}
    mockedGetTimeline.mockImplementation(
      (applicationId) =>
        new Promise((resolve) => {
          resolvers[applicationId] = resolve
        }),
    )

    const { rerender } = render(
      <CandidateActivityTimeline applicationId="app-1" />,
    )
    rerender(<CandidateActivityTimeline applicationId="app-2" />)

    resolvers['app-2']([
      activity({ id: 'b1', action_type: 'interview_scheduled' }),
    ])
    expect(await screen.findByText('Lên lịch phỏng vấn')).toBeInTheDocument()

    resolvers['app-1']([
      activity({ id: 'a1', action_type: 'candidate_withdrew' }),
    ])
    await waitFor(() => {
      expect(
        screen.queryByText('Bạn đã rút đơn ứng tuyển'),
      ).not.toBeInTheDocument()
    })
  })

  it('only uses the candidate-facing timeline endpoint', async () => {
    mockedGetTimeline.mockResolvedValue([activity({ id: 'a1' })])

    render(<CandidateActivityTimeline applicationId="app-1" />)

    await screen.findByText('Trạng thái đơn ứng tuyển được cập nhật')
    expect(applicationsApi.listApplicationActivities).not.toHaveBeenCalled()
    expect(applicationsApi.listApplicationNotes).not.toHaveBeenCalled()
    expect(applicationsApi.listApplicationEvaluations).not.toHaveBeenCalled()
    expect(applicationsApi.getApplicationMatch).not.toHaveBeenCalled()
    expect(applicationsApi.updateApplicationStatus).not.toHaveBeenCalled()
  })
})
