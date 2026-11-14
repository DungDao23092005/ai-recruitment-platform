import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { CandidateAIUsageHistoryTable } from '@/features/candidate/components/CandidateAIUsageHistoryTable'

vi.mock('@/api/subscriptions', async () => {
  const actual = await import('@/api/subscriptions')
  return {
    ...actual,
    getCandidateUsages: vi.fn(),
  }
})

const mockedGetCandidateUsages = (await import('@/api/subscriptions'))
  .getCandidateUsages as ReturnType<typeof vi.fn>

const usageResponse = {
  items: [
    {
      id: 'usage-1',
      subscription_id: 'sub-1',
      feature_type: 'candidate_parse_resume' as const,
      feature_label: 'Phân tích CV',
      amount: 2,
      status: 'completed' as const,
      status_label: 'Hoàn tất',
      reference_id: null,
      created_at: '2026-11-10T03:00:00Z',
      finalized_at: '2026-11-10T03:01:00Z',
    },
    {
      id: 'usage-2',
      subscription_id: 'sub-1',
      feature_type: 'candidate_chat' as const,
      feature_label: 'Trò chuyện AI',
      amount: 1,
      status: 'failed' as const,
      status_label: 'Thất bại',
      reference_id: null,
      created_at: '2026-11-09T03:00:00Z',
      finalized_at: '2026-11-09T03:01:00Z',
    },
  ],
  total: 12,
  page: 1,
  page_size: 10,
  total_pages: 2,
}

describe('CandidateAIUsageHistoryTable', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedGetCandidateUsages.mockResolvedValue(usageResponse)
  })

  it('renders candidate usage rows with the shared columns', async () => {
    render(<CandidateAIUsageHistoryTable />)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('Phân tích CV')).toBeInTheDocument()
    expect(within(table).getByText('Trò chuyện AI')).toBeInTheDocument()
    expect(within(table).getByText('Thời gian')).toBeInTheDocument()
    expect(within(table).getByText('Số lượt')).toBeInTheDocument()
    expect(within(table).getByText('Hoàn tất')).toBeInTheDocument()
    expect(within(table).getByText('Thất bại')).toBeInTheDocument()
    expect(screen.getByText(/Trang 1 \/ 2/)).toBeInTheDocument()
  })

  it('passes filters to the API and resets them', async () => {
    render(<CandidateAIUsageHistoryTable />)
    await screen.findByRole('table')

    fireEvent.change(screen.getByLabelText('Lọc theo tính năng'), {
      target: { value: 'candidate_chat' },
    })

    await waitFor(() =>
      expect(mockedGetCandidateUsages).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page: 1,
          page_size: 10,
          feature_type: 'candidate_chat',
        }),
      ),
    )

    fireEvent.change(screen.getByLabelText('Lọc theo trạng thái'), {
      target: { value: 'failed' },
    })
    await waitFor(() =>
      expect(mockedGetCandidateUsages).toHaveBeenLastCalledWith(
        expect.objectContaining({
          feature_type: 'candidate_chat',
          status: 'failed',
        }),
      ),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Đặt lại bộ lọc' }))
    await waitFor(() =>
      expect(mockedGetCandidateUsages).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
      }),
    )
  })

  it('paginates to the next page', async () => {
    render(<CandidateAIUsageHistoryTable />)
    await screen.findByRole('table')

    fireEvent.click(screen.getByRole('button', { name: 'Sau' }))

    await waitFor(() =>
      expect(mockedGetCandidateUsages).toHaveBeenLastCalledWith({
        page: 2,
        page_size: 10,
      }),
    )
  })

  it('renders an empty state', async () => {
    mockedGetCandidateUsages.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      total_pages: 0,
    })
    render(<CandidateAIUsageHistoryTable />)

    expect(
      await screen.findByText('Chưa có lịch sử sử dụng'),
    ).toBeInTheDocument()
  })

  it('renders an error banner and retries', async () => {
    mockedGetCandidateUsages.mockRejectedValueOnce({
      response: { status: 500, data: { detail: 'Tải thất bại' } },
    })
    render(<CandidateAIUsageHistoryTable />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Tải thất bại')
    fireEvent.click(screen.getByRole('button', { name: /Thử lại/ }))
    await waitFor(() =>
      expect(mockedGetCandidateUsages).toHaveBeenCalledTimes(2),
    )
  })
})
