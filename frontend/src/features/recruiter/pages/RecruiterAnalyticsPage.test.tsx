import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RecruiterAnalyticsPage } from './RecruiterAnalyticsPage'
import { getRecruiterAnalytics } from '@/api/analytics'
import type { RecruiterAnalytics } from '@/types/analytics'

vi.mock('@/api/analytics', () => ({
  getRecruiterAnalytics: vi.fn(),
}))

const mockedGetRecruiterAnalytics = vi.mocked(getRecruiterAnalytics)

const DATA: RecruiterAnalytics = {
  timezone: 'Asia/Ho_Chi_Minh',
  start_date: '2026-01-01',
  end_date: '2026-01-30',
  generated_at: '2026-01-30T10:00:00Z',
  kpis: {
    total_views: 1234,
    unique_views: 800,
    unverified_views: 12,
    total_applications: 50,
    hires: 5,
    conversion_rate: 10,
    avg_time_to_hire_days: 12.5,
  },
  funnel: [
    { stage: 'applied', count: 50 },
    { stage: 'under_review', count: 40 },
    { stage: 'interviewing', count: 20 },
    { stage: 'offered', count: 8 },
    { stage: 'accepted', count: 5 },
  ],
  daily_views: [
    { date: '2026-01-01', total_views: 500, unique_views: 300, unverified_views: 0 },
    { date: '2026-01-02', total_views: 734, unique_views: 500, unverified_views: 12 },
  ],
  jobs: [
    {
      job_id: 'job-1',
      job_title: 'Backend Engineer',
      job_status: 'published',
      total_views: 1234,
      unique_views: 800,
      unverified_views: 12,
      applications: 50,
      hires: 5,
    },
  ],
  quota: {
    subscription_status: 'active',
    plan_name: 'Pro',
    expires_at: '2026-02-28T00:00:00Z',
    job_posts: { limit: 10, used: 3, remaining: 7 },
    candidate_searches: { limit: 20, used: 5, remaining: 15 },
    ai_features: { limit: null, used: 9, remaining: null },
  },
  data_quality: {
    unique_views_reliable: false,
    raw_fallback_dates: ['2026-01-02'],
    note: 'Dữ liệu hôm nay lấy trực tiếp từ sự kiện thô.',
  },
}

const EMPTY_DATA: RecruiterAnalytics = {
  ...DATA,
  kpis: {
    total_views: 0,
    unique_views: 0,
    unverified_views: 0,
    total_applications: 0,
    hires: 0,
    conversion_rate: 0,
    avg_time_to_hire_days: null,
  },
  funnel: DATA.funnel.map((stage) => ({ ...stage, count: 0 })),
  daily_views: [],
  jobs: [],
  quota: {
    subscription_status: 'none',
    plan_name: null,
    expires_at: null,
    job_posts: { limit: null, used: 0, remaining: null },
    candidate_searches: { limit: null, used: 0, remaining: null },
    ai_features: { limit: null, used: 0, remaining: null },
  },
  data_quality: {
    unique_views_reliable: true,
    raw_fallback_dates: [],
    note: 'Chưa có dữ liệu.',
  },
}

function createAxiosError(status: number, message = 'Request failed') {
  const error = new Error(message)
  Object.assign(error, {
    isAxiosError: true,
    response: { status, data: { detail: message } },
    config: {},
  })
  return error
}

function renderPage() {
  return render(
    <MemoryRouter>
      <RecruiterAnalyticsPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RecruiterAnalyticsPage', () => {
  it('renders KPIs, funnel, daily chart, per-job table and quota', async () => {
    mockedGetRecruiterAnalytics.mockResolvedValueOnce(DATA)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Phân tích tuyển dụng')).toBeInTheDocument()
    })

    expect(screen.getByText('Lượt xem tin')).toBeInTheDocument()
    expect(screen.getAllByText('1.234')).toHaveLength(2)
    expect(screen.getByText('800 lượt xem duy nhất')).toBeInTheDocument()
    expect(screen.getByText('Tỷ lệ chuyển đổi 10.0%')).toBeInTheDocument()
    expect(screen.getByText('Thời gian tuyển dụng TB 12.5 ngày')).toBeInTheDocument()

    expect(screen.getByRole('img', { name: 'Đã nộp: 50' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Phỏng vấn: 20' })).toBeInTheDocument()
    expect(
      screen.getByRole('img', { name: 'Biểu đồ lượt xem theo ngày' }),
    ).toBeInTheDocument()

    expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    expect(screen.getByText('published')).toBeInTheDocument()
    expect(screen.getByText('3 / 10')).toBeInTheDocument()
    expect(screen.getByText('9 đã dùng · Không giới hạn')).toBeInTheDocument()
    expect(
      screen.getByText('Lượt xem duy nhất chưa đầy đủ'),
    ).toBeInTheDocument()
    expect(screen.getAllByText(/2026-01-02/)).toHaveLength(2)
  })

  it('shows the no-company empty state on 404', async () => {
    mockedGetRecruiterAnalytics.mockRejectedValueOnce(
      createAxiosError(404, 'Not Found'),
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Chưa có công ty')).toBeInTheDocument()
    })
    const link = screen.getByRole('button', { name: 'Tạo công ty' }).closest('a')
    expect(link).toHaveAttribute('href', '/recruiter/company')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows an empty analytics state when there is no data yet', async () => {
    mockedGetRecruiterAnalytics.mockResolvedValueOnce(EMPTY_DATA)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Chưa có dữ liệu phân tích')).toBeInTheDocument()
    })
    expect(screen.queryByText('Lượt xem tin')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Đăng tin tuyển dụng' }).closest('a'),
    ).toHaveAttribute('href', '/recruiter/jobs/new')
  })

  it('shows an error banner and retries on failure', async () => {
    mockedGetRecruiterAnalytics
      .mockRejectedValueOnce(createAxiosError(500, 'Internal Server Error'))
      .mockResolvedValueOnce(DATA)

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Hệ thống đang gặp sự cố',
      )
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('Lượt xem tin')).toBeInTheDocument()
    })
    expect(mockedGetRecruiterAnalytics).toHaveBeenCalledTimes(2)
  })

  it('applies the selected date range as query parameters', async () => {
    mockedGetRecruiterAnalytics.mockResolvedValue(DATA)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Lượt xem tin')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Từ ngày'), {
      target: { value: '2026-01-01' },
    })
    fireEvent.change(screen.getByLabelText('Đến ngày'), {
      target: { value: '2026-01-31' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Áp dụng/i }))

    await waitFor(() => {
      expect(mockedGetRecruiterAnalytics).toHaveBeenLastCalledWith({
        start_date: '2026-01-01',
        end_date: '2026-01-31',
      })
    })
  })

  it('shows a call-to-action when the recruiter has no active plan', async () => {
    mockedGetRecruiterAnalytics.mockResolvedValueOnce({
      ...DATA,
      quota: EMPTY_DATA.quota,
    })

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Bạn chưa có gói dịch vụ đang hoạt động.'),
      ).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: 'Xem các gói' }).closest('a'),
    ).toHaveAttribute('href', '/plans')
  })
})
