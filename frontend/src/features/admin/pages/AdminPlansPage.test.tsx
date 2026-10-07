import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { AdminPlansPage } from '@/features/admin/pages/AdminPlansPage'
import { getAdminPlans } from '@/api/admin'
import type { AdminPlanRead } from '@/types/admin'

vi.mock('@/api/admin')

const mockPlans: AdminPlanRead[] = [
  {
    id: 'plan-1',
    name: 'Gói cơ bản',
    description: 'Mô tả gói cơ bản',
    price: 99000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 5,
    max_candidate_searches: 20,
    max_ai_features: 5,
    display_order: 1,
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'plan-2',
    name: 'Gói nâng cao',
    description: 'Mô tả gói nâng cao',
    price: 299000,
    currency: 'VND',
    duration_days: 60,
    max_job_posts: 20,
    max_candidate_searches: 100,
    max_ai_features: 20,
    display_order: 2,
    is_active: false,
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
]

describe('AdminPlansPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders page header correctly', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlans)

    render(<AdminPlansPage />)

    await waitFor(() => {
      expect(screen.getByText('Quản lý các gói tuyển dụng cho nhà tuyển dụng')).toBeInTheDocument()
    })

    // Header button "Tạo gói mới" should be visible
    expect(screen.getByRole('button', { name: /tạo gói tuyển dụng mới/i })).toBeInTheDocument()
  })

  it('clicking "+ Tạo gói" button opens Create modal', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlans)

    render(<AdminPlansPage />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /tạo gói tuyển dụng mới/i })).toBeInTheDocument()
    })

    // Click "+ Tạo gói" button (by aria-label)
    const createButton = screen.getByRole('button', { name: /tạo gói tuyển dụng mới/i })
    fireEvent.click(createButton)

    // Create modal should now be open (check for modal title in dialog)
    await waitFor(() => {
      const dialog = screen.getByRole('dialog')
      expect(dialog).toBeInTheDocument()
      expect(dialog).toHaveTextContent('Tạo gói mới')
    })
  })

  it('cancel closes Create modal', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlans)

    render(<AdminPlansPage />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /tạo gói tuyển dụng mới/i })).toBeInTheDocument()
    })

    // Open create modal
    fireEvent.click(screen.getByRole('button', { name: /tạo gói tuyển dụng mới/i }))

    await waitFor(() => {
      const dialog = screen.getByRole('dialog')
      expect(dialog).toBeInTheDocument()
    })

    // Click cancel (Đóng)
    fireEvent.click(screen.getByRole('button', { name: /đóng/i }))

    // Modal should be closed
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('edit flow still works', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlans)

    render(<AdminPlansPage />)

    await waitFor(() => {
      expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
    })

    // Click edit button on first plan
    const editButtons = screen.getAllByRole('button', { name: /sửa gói/i })
    expect(editButtons.length).toBeGreaterThan(0)
    fireEvent.click(editButtons[0])

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByRole('dialog')).toHaveTextContent('Sửa gói')
    })

    // Close edit modal
    fireEvent.click(screen.getByRole('button', { name: /hủy/i }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('status toggle still works', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlans)

    render(<AdminPlansPage />)

    await waitFor(() => {
      expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
    })

    // Click status button on first plan
    const statusButtons = screen.getAllByRole('button', { name: /khóa gói/i })
    expect(statusButtons.length).toBeGreaterThan(0)
    fireEvent.click(statusButtons[0])

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByRole('dialog')).toHaveTextContent('Thay đổi trạng thái')
    })

    // Close status modal
    fireEvent.click(screen.getByRole('button', { name: /hủy/i }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('API error is rendered safely', async () => {
    vi.mocked(getAdminPlans).mockRejectedValue(new Error('Network error'))

    render(<AdminPlansPage />)

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })
  })
})