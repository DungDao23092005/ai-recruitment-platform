import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ApplicationStatusChart } from './ApplicationStatusChart'
import type { ApplicationStatusCounts } from '@/types/admin'

const mockCounts: ApplicationStatusCounts = {
  applied: 5,
  under_review: 4,
  shortlisted: 3,
  interviewing: 2,
  accepted: 2,
  rejected: 3,
  withdrawn: 1,
}

const emptyCounts: ApplicationStatusCounts = {
  applied: 0,
  under_review: 0,
  shortlisted: 0,
  interviewing: 0,
  accepted: 0,
  rejected: 0,
  withdrawn: 0,
}

describe('ApplicationStatusChart', () => {
  it('renders all status labels', () => {
    render(<ApplicationStatusChart counts={mockCounts} />)
    expect(screen.getByText('Đã nộp')).toBeInTheDocument()
    expect(screen.getByText('Đang xem xét')).toBeInTheDocument()
    expect(screen.getByText('Lọt vòng ngắn')).toBeInTheDocument()
    expect(screen.getByText('Đang phỏng vấn')).toBeInTheDocument()
    expect(screen.getByText('Đã chấp nhận')).toBeInTheDocument()
    expect(screen.getByText('Từ chối')).toBeInTheDocument()
    expect(screen.getByText('Đã rút')).toBeInTheDocument()
  })

  it('renders counts and percentages', () => {
    render(<ApplicationStatusChart counts={mockCounts} />)
    expect(screen.getByText('5 (25%)')).toBeInTheDocument()
    expect(screen.getByText('1 (5%)')).toBeInTheDocument()
  })

  it('shows an empty state when total is zero', () => {
    render(<ApplicationStatusChart counts={emptyCounts} />)
    expect(
      screen.getByText('Chưa có dữ liệu đơn ứng tuyển.'),
    ).toBeInTheDocument()
  })
})