import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PlanCard } from '@/features/subscriptions/components/PlanCard'
import type { RecruitmentPlanRead } from '@/types/subscription'

const candidatePlan: RecruitmentPlanRead = {
  id: 'plan-candidate',
  name: 'Gói AI Pro',
  description: 'Gói AI dành cho ứng viên',
  price: 99000,
  currency: 'VND',
  duration_days: 30,
  max_job_posts: 0,
  max_candidate_searches: 0,
  max_ai_features: 25,
  plan_audience: 'candidate',
  is_free: false,
  is_active: true,
}

const companyPlan: RecruitmentPlanRead = {
  id: 'plan-company',
  name: 'Gói Tuyển dụng',
  description: 'Gói dành cho doanh nghiệp',
  price: 5000000,
  currency: 'VND',
  duration_days: 30,
  max_job_posts: 10,
  max_candidate_searches: 50,
  max_ai_features: 20,
  plan_audience: 'company',
  is_free: false,
  is_active: true,
}

describe('PlanCard', () => {
  it('renders candidate AI benefits without company counters', () => {
    render(<PlanCard plan={candidatePlan} onSelect={vi.fn()} />)

    expect(screen.getByText('Gói dịch vụ AI')).toBeInTheDocument()
    expect(screen.getByText('25')).toBeInTheDocument()
    expect(screen.getByText('lượt AI dùng chung')).toBeInTheDocument()
    expect(
      screen.getByText(/Một hạn mức AI dùng chung cho Phân tích CV/),
    ).toBeInTheDocument()
    expect(screen.queryByText('bài đăng tin')).not.toBeInTheDocument()
    expect(screen.queryByText('tìm kiếm ứng viên')).not.toBeInTheDocument()
  })

  it('keeps the company plan rendering unchanged', () => {
    render(<PlanCard plan={companyPlan} onSelect={vi.fn()} />)

    expect(screen.getByText('Gói tuyển dụng')).toBeInTheDocument()
    expect(screen.getByText('bài đăng tin')).toBeInTheDocument()
    expect(screen.getByText('tìm kiếm ứng viên')).toBeInTheDocument()
    expect(screen.getByText('tính năng AI')).toBeInTheDocument()
    expect(
      screen.queryByText(/Một hạn mức AI dùng chung/),
    ).not.toBeInTheDocument()
  })

  it('invokes onSelect for an available plan', () => {
    const onSelect = vi.fn()
    render(<PlanCard plan={candidatePlan} onSelect={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: /Chọn gói Gói AI Pro/ }))
    expect(onSelect).toHaveBeenCalledWith('plan-candidate')
  })

  it('does not invoke onSelect when disabled', () => {
    const onSelect = vi.fn()
    render(
      <PlanCard
        plan={candidatePlan}
        onSelect={onSelect}
        disabled
        disabledReason="Không khả dụng"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Không khả dụng/ }))
    expect(onSelect).not.toHaveBeenCalled()
  })
})
