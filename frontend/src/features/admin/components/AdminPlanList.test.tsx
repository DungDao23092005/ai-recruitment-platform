import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import { AdminPlanList } from '@/features/admin/components/AdminPlanList'
import { getAdminPlans } from '@/api/admin'
import type { AdminPlanList as AdminPlanListResponse, AdminPlanRead } from '@/types/admin'

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

function makeResponse(
  items: AdminPlanRead[] = mockPlans,
  total = items.length,
  skip = 0,
  limit = 10,
): AdminPlanListResponse {
  return { items, total, skip, limit }
}

describe('AdminPlanList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state with []', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(makeResponse([]))

    render(<AdminPlanList onEdit={vi.fn()} onStatus={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Không tìm thấy gói')).toBeInTheDocument()
      expect(screen.getByText('Chưa có gói tuyển dụng nào trên nền tảng.')).toBeInTheDocument()
    })
  })

  it('renders multiple plans', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(makeResponse())

    render(<AdminPlanList onEdit={vi.fn()} onStatus={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      expect(screen.getByText('Gói nâng cao')).toBeInTheDocument()
      expect(screen.getByText('VND 99,000')).toBeInTheDocument()
      expect(screen.getByText('VND 299,000')).toBeInTheDocument()
    })
  })

  it('renders active/inactive status', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(makeResponse())

    render(<AdminPlanList onEdit={vi.fn()} onStatus={vi.fn()} />)

    await waitFor(() => {
      // Check for status badges (not buttons)
      const activeBadge = screen.getByText('Hoạt động')
      expect(activeBadge).toBeInTheDocument()
      // Check that the badge is a badge component (not a button)
      expect(activeBadge.tagName).toBe('DIV')
    })
  })

  it('uses total from the API to render pagination', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(makeResponse(mockPlans, 25))

    render(<AdminPlanList onEdit={vi.fn()} onStatus={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Trang 1 / 3')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))

    await waitFor(() => {
      expect(getAdminPlans).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 10, limit: 10 }),
      )
    })
  })

  it('resets to the first page and sends the trimmed search query', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(makeResponse(mockPlans, 25))

    render(<AdminPlanList onEdit={vi.fn()} onStatus={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Trang 1 / 3')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
    await waitFor(() => {
      expect(getAdminPlans).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 10 }),
      )
    })

    fireEvent.change(screen.getByLabelText('Tìm theo tên gói'), {
      target: { value: '  nâng cao  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Tìm kiếm' }))

    await waitFor(() => {
      expect(getAdminPlans).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 0, search: 'nâng cao' }),
      )
    })
  })
})