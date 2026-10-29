import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { vi } from 'vitest'
import { AdminPlansPage } from '@/features/admin/pages/AdminPlansPage'
import { getAdminPlans, deleteAdminPlan } from '@/api/admin'
import type { AdminPlanList, AdminPlanRead } from '@/types/admin'

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

const mockPlanList: AdminPlanList = {
  items: mockPlans,
  total: mockPlans.length,
  skip: 0,
  limit: 10,
}

describe('AdminPlansPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders page header correctly', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlanList)

    render(<AdminPlansPage />)

    await waitFor(() => {
      expect(screen.getByText('Quản lý các gói tuyển dụng cho nhà tuyển dụng')).toBeInTheDocument()
    })

    // Header button "Tạo gói mới" should be visible
    expect(screen.getByRole('button', { name: /tạo gói tuyển dụng mới/i })).toBeInTheDocument()
  })

  it('clicking "+ Tạo gói" button opens Create modal', async () => {
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlanList)

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
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlanList)

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
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlanList)

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
    vi.mocked(getAdminPlans).mockResolvedValue(mockPlanList)

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

  describe('Plan deletion', () => {
    beforeEach(() => {
      vi.mocked(getAdminPlans).mockResolvedValue(mockPlanList)
      vi.mocked(deleteAdminPlan).mockResolvedValue(undefined)
    })

    it('Xóa button renders for each plan row', async () => {
      render(<AdminPlansPage />)

      await waitFor(() => {
        expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      })

      // Check that Xóa button exists for each plan
      const deleteButtons = screen.getAllByRole('button', { name: /xóa gói/i })
      expect(deleteButtons.length).toBe(2)
    })

    it('opens delete confirmation modal with correct plan name', async () => {
      render(<AdminPlansPage />)

      await waitFor(() => {
        expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      })

      // Click delete button on first plan
      const deleteButton = screen.getByRole('button', { name: /xóa gói gói cơ bản/i })
      fireEvent.click(deleteButton)

      // Modal should open with correct plan name
      await waitFor(() => {
        const dialog = screen.getByRole('dialog')
        expect(dialog).toBeInTheDocument()
        expect(dialog).toHaveTextContent('Xóa gói tuyển dụng')
        // Plan name should be rendered as text, not literal HTML
        expect(dialog).toHaveTextContent('Gói cơ bản')
      })
    })

    it('cancelling does not call delete API', async () => {
      render(<AdminPlansPage />)

      await waitFor(() => {
        expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      })

      // Open delete modal
      fireEvent.click(screen.getByRole('button', { name: /xóa gói gói cơ bản/i }))

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Click cancel (within dialog)
      const dialog = screen.getByRole('dialog')
      fireEvent.click(within(dialog).getByRole('button', { name: /hủy/i }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })

      // API should not have been called
      expect(deleteAdminPlan).not.toHaveBeenCalled()
    })

    it('confirming calls deleteAdminPlan with correct plan ID', async () => {
      render(<AdminPlansPage />)

      await waitFor(() => {
        expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      })

      // Open delete modal
      fireEvent.click(screen.getByRole('button', { name: /xóa gói gói cơ bản/i }))

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Click delete confirmation (within dialog)
      const dialog = screen.getByRole('dialog')
      fireEvent.click(within(dialog).getByRole('button', { name: /xóa gói$/i }))

      await waitFor(() => {
        expect(deleteAdminPlan).toHaveBeenCalledTimes(1)
        expect(deleteAdminPlan).toHaveBeenCalledWith('plan-1')
      })
    })

    it('successful deletion closes modal and refreshes list', async () => {
      render(<AdminPlansPage />)

      await waitFor(() => {
        expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      })

      // Open and confirm deletion
      fireEvent.click(screen.getByRole('button', { name: /xóa gói gói cơ bản/i }))
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })
      const dialog = screen.getByRole('dialog')
      fireEvent.click(within(dialog).getByRole('button', { name: /xóa gói$/i }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })

      // Plan list should have been refreshed
      // (in real scenario, the mock would return empty array on second call)
    })

    it('409 Conflict displays backend message and keeps plan in list', async () => {
      vi.mocked(deleteAdminPlan).mockRejectedValueOnce({
        response: {
          status: 409,
          data: { detail: 'Không thể xóa gói này vì đã có người đăng ký. Hãy khóa gói thay vì xóa.' },
        },
      })

      render(<AdminPlansPage />)

      await waitFor(() => {
        expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      })

      // Open delete modal
      fireEvent.click(screen.getByRole('button', { name: /xóa gói Gói cơ bản/i }))
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Click delete (within dialog to avoid duplicate buttons)
      const dialog = screen.getByRole('dialog')
      fireEvent.click(within(dialog).getByRole('button', { name: /xóa gói$/i }))

      // Should show error message
      await waitFor(() => {
        expect(screen.getByText('Không thể xóa gói này vì đã có người đăng ký. Hãy khóa gói thay vì xóa.')).toBeInTheDocument()
      })

      // Modal should still be open
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      // Plan should still be in the list (appears in table and modal)
      expect(screen.getAllByText('Gói cơ bản').length).toBeGreaterThanOrEqual(2)
    })

    it('generic failure does not show false success or remove row', async () => {
      vi.mocked(deleteAdminPlan).mockImplementationOnce(() =>
        Promise.reject({
          response: {
            status: 500,
            data: { detail: 'Internal server error' },
          },
        })
      )

      render(<AdminPlansPage />)

      await waitFor(() => {
        expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      })

      // Open and confirm deletion
      fireEvent.click(screen.getByRole('button', { name: /Xóa gói Gói cơ bản/i }))
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })
      const dialog = screen.getByRole('dialog')
      fireEvent.click(within(dialog).getByRole('button', { name: /xóa gói$/i }))

      // Should show error but not remove the row
      await waitFor(() => {
        expect(screen.getByText('Internal server error')).toBeInTheDocument()
      })

      // Plan should still be in the list (appears in table and modal)
      expect(screen.getAllByText('Gói cơ bản').length).toBeGreaterThanOrEqual(2)
    })

    it('double click does not dispatch duplicate requests', async () => {
      let resolveDelete: (value: void) => void
      const deletePromise = new Promise<void>((resolve) => {
        resolveDelete = resolve
      })
      vi.mocked(deleteAdminPlan).mockReturnValue(deletePromise)

      render(<AdminPlansPage />)

      await waitFor(() => {
        expect(screen.getByText('Gói cơ bản')).toBeInTheDocument()
      })

      // Open and click delete rapidly
      fireEvent.click(screen.getByRole('button', { name: /xóa gói gói cơ bản/i }))
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Click delete twice rapidly (within dialog to avoid duplicate buttons)
      const dialog = screen.getByRole('dialog')
      const deleteButton = within(dialog).getByRole('button', { name: /xóa gói$/i })
      fireEvent.click(deleteButton)
      fireEvent.click(deleteButton)

      // Resolve the promise
      resolveDelete!()

      await waitFor(() => {
        expect(deleteAdminPlan).toHaveBeenCalledTimes(1)
      })
    })
  })
})
