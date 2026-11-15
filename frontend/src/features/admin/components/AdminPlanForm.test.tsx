import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import { AdminPlanForm } from '@/features/admin/components/AdminPlanForm'
import {
  createAdminPlan,
  updateAdminPlan,
  updateAdminPlanStatus,
} from '@/api/admin'
import type { AdminPlanRead } from '@/types/admin'

vi.mock('@/api/admin')

function makePlan(overrides: Partial<AdminPlanRead> = {}): AdminPlanRead {
  return {
    id: 'plan-1',
    name: 'Gói doanh nghiệp',
    description: 'Mô tả gói',
    price: 99000,
    currency: 'VND',
    duration_days: 30,
    max_job_posts: 10,
    max_candidate_searches: 50,
    max_ai_features: 10,
    plan_audience: 'company',
    is_free: false,
    display_order: 0,
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

function changeField(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

function inputValue(label: RegExp): string {
  return (screen.getByLabelText(label) as HTMLInputElement).value
}

function submitCreate() {
  fireEvent.click(screen.getByRole('button', { name: /^Tạo gói$/ }))
}

function submitEdit() {
  fireEvent.click(screen.getByRole('button', { name: /^Cập nhật$/ }))
}

function expectRecruitmentFieldsHidden() {
  expect(screen.queryByLabelText(/Số lượng bài đăng/)).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/Số tìm kiếm ứng viên/)).not.toBeInTheDocument()
}

function expectRecruitmentFieldsVisible() {
  expect(screen.getByLabelText(/Số lượng bài đăng/)).toBeInTheDocument()
  expect(screen.getByLabelText(/Số tìm kiếm ứng viên/)).toBeInTheDocument()
}

describe('AdminPlanForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(createAdminPlan).mockResolvedValue(makePlan())
    vi.mocked(updateAdminPlan).mockResolvedValue(makePlan())
    vi.mocked(updateAdminPlanStatus).mockResolvedValue(makePlan())
  })

  describe('create', () => {
    it('shows recruitment quotas and the Company AI label by default', () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      expectRecruitmentFieldsVisible()
      expect(screen.getByLabelText(/Lượt AI tuyển dụng/)).toBeInTheDocument()
      expect(
        screen.getByText(/các tính năng AI phục vụ tuyển dụng/),
      ).toBeInTheDocument()
    })

    it('hides recruitment quota controls for Candidate Free', () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_free' },
      })

      expectRecruitmentFieldsHidden()
    })

    it('shows the shared Candidate AI label and helper text for Candidate Free', () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_free' },
      })

      expect(
        screen.getByLabelText(/Hạn mức AI ứng viên \(Lượt AI dùng chung\)/),
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          'Một hạn mức AI dùng chung cho Phân tích CV, Gợi ý việc làm và Trò chuyện AI.',
        ),
      ).toBeInTheDocument()
    })

    it('fixes Candidate Free price at 0 and disables it', () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_free' },
      })

      const priceInput = screen.getByLabelText(/Giá \(VND\)/) as HTMLInputElement
      expect(priceInput.value).toBe('0')
      expect(priceInput).toBeDisabled()
    })

    it('submits zero recruitment quotas and the Candidate AI quota for Candidate Free', async () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      changeField(/Tên gói/, 'Gói ứng viên miễn phí')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_free' },
      })
      changeField(/Hạn mức AI ứng viên/, '15')

      submitCreate()

      await waitFor(() => {
        expect(createAdminPlan).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Gói ứng viên miễn phí',
            price: 0,
            plan_audience: 'candidate',
            is_free: true,
            max_job_posts: 0,
            max_candidate_searches: 0,
            max_ai_features: 15,
          }),
        )
      })
    })

    it('hides recruitment quotas and accepts a paid price for Candidate Paid', async () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      changeField(/Tên gói/, 'Gói ứng viên trả phí')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_paid' },
      })
      expectRecruitmentFieldsHidden()
      changeField(/Giá \(VND\)/, '49000')
      changeField(/Hạn mức AI ứng viên/, '30')

      submitCreate()

      await waitFor(() => {
        expect(createAdminPlan).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Gói ứng viên trả phí',
            price: 49000,
            plan_audience: 'candidate',
            is_free: false,
            max_job_posts: 0,
            max_candidate_searches: 0,
            max_ai_features: 30,
          }),
        )
      })
    })
  })

  describe('edit', () => {
    it('loads existing recruitment quotas and the Company AI label', () => {
      render(
        <AdminPlanForm
          mode="edit"
          defaultPlan={makePlan({
            max_job_posts: 7,
            max_candidate_searches: 40,
            max_ai_features: 9,
          })}
          onClose={vi.fn()}
        />,
      )

      expectRecruitmentFieldsVisible()
      expect(screen.getByLabelText(/Lượt AI tuyển dụng/)).toBeInTheDocument()
      expect(inputValue(/Số lượng bài đăng/)).toBe('7')
      expect(inputValue(/Số tìm kiếm ứng viên/)).toBe('40')
      expect(inputValue(/Lượt AI tuyển dụng/)).toBe('9')
    })

    it('loads max_ai_features as the Candidate AI quota for Candidate Free', () => {
      render(
        <AdminPlanForm
          mode="edit"
          defaultPlan={makePlan({
            plan_audience: 'candidate',
            is_free: true,
            price: 0,
            max_job_posts: 0,
            max_candidate_searches: 0,
            max_ai_features: 25,
          })}
          onClose={vi.fn()}
        />,
      )

      expectRecruitmentFieldsHidden()
      expect(inputValue(/Hạn mức AI ứng viên/)).toBe('25')
      expect(
        screen.getByLabelText(/Giá \(VND\)/) as HTMLInputElement,
      ).toBeDisabled()
    })

    it('loads the Candidate AI quota for Candidate Paid', () => {
      render(
        <AdminPlanForm
          mode="edit"
          defaultPlan={makePlan({
            plan_audience: 'candidate',
            is_free: false,
            price: 49000,
            max_job_posts: 0,
            max_candidate_searches: 0,
            max_ai_features: 30,
          })}
          onClose={vi.fn()}
        />,
      )

      expectRecruitmentFieldsHidden()
      expect(inputValue(/Hạn mức AI ứng viên/)).toBe('30')
      expect(inputValue(/Giá \(VND\)/)).toBe('49000')
    })

    it('does not reintroduce stale recruitment quotas when submitting Candidate edits', async () => {
      const candidatePlan = makePlan({
        plan_audience: 'candidate',
        is_free: false,
        price: 49000,
        max_job_posts: 5,
        max_candidate_searches: 6,
        max_ai_features: 30,
      })

      render(
        <AdminPlanForm
          mode="edit"
          defaultPlan={candidatePlan}
          planId={candidatePlan.id}
          onClose={vi.fn()}
        />,
      )

      expectRecruitmentFieldsHidden()
      submitEdit()

      await waitFor(() => {
        expect(updateAdminPlan).toHaveBeenCalledWith(
          candidatePlan.id,
          expect.objectContaining({
            plan_audience: 'candidate',
            max_job_posts: 0,
            max_candidate_searches: 0,
            max_ai_features: 30,
          }),
        )
      })
    })
  })

  describe('switching plan types', () => {
    it('resets recruitment quota payload values when switching Company to Candidate', async () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      changeField(/Tên gói/, 'Gói chuyển đổi')
      changeField(/Số lượng bài đăng/, '12')
      changeField(/Số tìm kiếm ứng viên/, '60')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_paid' },
      })
      changeField(/Giá \(VND\)/, '1000')

      submitCreate()

      await waitFor(() => {
        expect(createAdminPlan).toHaveBeenCalledWith(
          expect.objectContaining({
            max_job_posts: 0,
            max_candidate_searches: 0,
          }),
        )
      })
    })

    it('restores previously entered Company quotas when switching back', () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      changeField(/Số lượng bài đăng/, '7')
      changeField(/Số tìm kiếm ứng viên/, '40')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_free' },
      })
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'company' },
      })

      expect(inputValue(/Số lượng bài đăng/)).toBe('7')
      expect(inputValue(/Số tìm kiếm ứng viên/)).toBe('40')
    })

    it('uses Company defaults when no previous Company quotas exist', () => {
      render(
        <AdminPlanForm
          mode="edit"
          defaultPlan={makePlan({
            plan_audience: 'candidate',
            is_free: true,
            price: 0,
            max_job_posts: 0,
            max_candidate_searches: 0,
            max_ai_features: 25,
          })}
          onClose={vi.fn()}
        />,
      )

      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'company' },
      })

      expect(inputValue(/Số lượng bài đăng/)).toBe('10')
      expect(inputValue(/Số tìm kiếm ứng viên/)).toBe('50')
    })

    it('does not leak recruitment quotas between Candidate Free and Candidate Paid', async () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      changeField(/Tên gói/, 'Gói ứng viên')
      changeField(/Số lượng bài đăng/, '5')
      changeField(/Số tìm kiếm ứng viên/, '20')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_free' },
      })
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_paid' },
      })
      changeField(/Giá \(VND\)/, '1000')

      expectRecruitmentFieldsHidden()
      submitCreate()

      await waitFor(() => {
        expect(createAdminPlan).toHaveBeenCalledWith(
          expect.objectContaining({
            max_job_posts: 0,
            max_candidate_searches: 0,
          }),
        )
      })
    })

    it('restores an editable, validated price when moving from Candidate Free to Candidate Paid', async () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      changeField(/Tên gói/, 'Gói ứng viên')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_free' },
      })
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_paid' },
      })

      const priceInput = screen.getByLabelText(/Giá \(VND\)/) as HTMLInputElement
      expect(priceInput).not.toBeDisabled()

      changeField(/Giá \(VND\)/, '0')
      submitCreate()

      expect(
        await screen.findByText('Gói trả phí phải có giá lớn hơn 0'),
      ).toBeInTheDocument()
      expect(createAdminPlan).not.toHaveBeenCalled()

      changeField(/Giá \(VND\)/, '25000')
      submitCreate()

      await waitFor(() => {
        expect(createAdminPlan).toHaveBeenCalledWith(
          expect.objectContaining({ price: 25000, is_free: false }),
        )
      })
    })

    it('keeps max_ai_features intact while switching plan types', () => {
      render(<AdminPlanForm mode="create" onClose={vi.fn()} />)

      changeField(/Lượt AI tuyển dụng/, '20')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_free' },
      })
      expect(inputValue(/Hạn mức AI ứng viên/)).toBe('20')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'candidate_paid' },
      })
      expect(inputValue(/Hạn mức AI ứng viên/)).toBe('20')
      fireEvent.change(screen.getByLabelText(/Loại gói/), {
        target: { value: 'company' },
      })
      expect(inputValue(/Lượt AI tuyển dụng/)).toBe('20')
    })
  })
})
