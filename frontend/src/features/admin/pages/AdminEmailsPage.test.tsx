import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { AdminEmailsPage } from '@/features/admin/pages/AdminEmailsPage'
import { getAdminEmails, getAdminEmailStats, retryAdminEmail } from '@/api/admin'
import type {
  AdminEmailOutboxList,
  AdminEmailOutboxMessage,
  AdminEmailOutboxStats,
} from '@/types/admin'

vi.mock('@/api/admin')

const mockMessage: AdminEmailOutboxMessage = {
  id: 'msg-1',
  event_type: 'subscription_activated',
  to_email: 'buyer@example.com',
  subject: 'Kích hoạt gói dịch vụ',
  status: 'failed',
  attempts: 3,
  max_attempts: 3,
  next_attempt_at: '2026-01-02T00:00:00Z',
  processing_started_at: null,
  sent_at: null,
  last_error: 'SMTP timeout',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
}

const mockList: AdminEmailOutboxList = {
  items: [mockMessage],
  total: 1,
  skip: 0,
  limit: 10,
}

const mockStats: AdminEmailOutboxStats = {
  pending: 2,
  processing: 1,
  sent: 10,
  failed: 3,
  total: 16,
  oldest_pending_created_at: '2026-01-01T00:00:00Z',
}

describe('AdminEmailsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getAdminEmails).mockResolvedValue(mockList)
    vi.mocked(getAdminEmailStats).mockResolvedValue(mockStats)
    vi.mocked(retryAdminEmail).mockResolvedValue({ ...mockMessage, status: 'pending' })
  })

  it('renders header, stats and message rows', async () => {
    render(<AdminEmailsPage />)

    expect(screen.getByText('Hàng đợi email')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    expect(screen.getByText('Kích hoạt gói dịch vụ')).toBeInTheDocument()
    expect(screen.getByText('subscription_activated')).toBeInTheDocument()
    expect(screen.getByText('SMTP timeout')).toBeInTheDocument()
    expect(screen.getByText('3/3')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('16')).toBeInTheDocument()
    })
    expect(screen.getAllByText('Đã gửi').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Thất bại').length).toBeGreaterThan(0)
  })

  it('searches by email or subject', async () => {
    render(<AdminEmailsPage />)
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Tìm theo email hoặc tiêu đề'), {
      target: { value: 'buyer@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /tìm kiếm/i }))

    await waitFor(() => {
      expect(getAdminEmails).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'buyer@example.com' }),
      )
    })
  })

  it('filters by status', async () => {
    render(<AdminEmailsPage />)
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Lọc theo trạng thái'), {
      target: { value: 'failed' },
    })

    await waitFor(() => {
      expect(getAdminEmails).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'failed' }),
      )
    })
  })

  it('renders list API error safely', async () => {
    vi.mocked(getAdminEmails).mockRejectedValueOnce(new Error('boom'))
    render(<AdminEmailsPage />)

    await waitFor(() => {
      expect(
        screen.getByText(
          'Không thể kết nối tới máy chủ. Vui lòng kiểm tra kết nối và thử lại.',
        ),
      ).toBeInTheDocument()
    })
  })

  it('renders a stats error banner without breaking the list', async () => {
    vi.mocked(getAdminEmailStats).mockRejectedValueOnce(new Error('boom'))
    render(<AdminEmailsPage />)

    await waitFor(() => {
      expect(
        screen.getByText('Không thể tải số liệu hàng đợi email.'),
      ).toBeInTheDocument()
    })
    expect(await screen.findByText('buyer@example.com')).toBeInTheDocument()
  })

  it('retries a failed message', async () => {
    render(<AdminEmailsPage />)
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /gửi lại email msg-1/i }))

    await waitFor(() => {
      expect(retryAdminEmail).toHaveBeenCalledWith('msg-1')
    })
  })

  it('disables retry while a message is being processed', async () => {
    vi.mocked(getAdminEmails).mockResolvedValueOnce({
      ...mockList,
      items: [{ ...mockMessage, status: 'processing' }],
    })

    render(<AdminEmailsPage />)
    await waitFor(() => {
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('button', { name: /gửi lại email msg-1/i }),
    ).toBeDisabled()
  })
})
