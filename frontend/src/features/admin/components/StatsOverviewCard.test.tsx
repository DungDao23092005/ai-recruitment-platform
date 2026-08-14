import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StatsOverviewCard } from './StatsOverviewCard'
import type { AdminStats } from '@/types/admin'

const mockStats: AdminStats = {
  total_users: 10,
  total_candidates: 5,
  total_recruiters: 4,
  total_admins: 1,
  total_companies: 3,
  total_jobs: 7,
  total_applications: 20,
  applications_by_status: {
    applied: 5,
    under_review: 4,
    shortlisted: 3,
    interviewing: 2,
    accepted: 2,
    rejected: 3,
    withdrawn: 1,
  },
}

describe('StatsOverviewCard', () => {
  it('renders all stat labels', () => {
    render(<StatsOverviewCard stats={mockStats} />)
    expect(screen.getByText('Tổng người dùng')).toBeInTheDocument()
    expect(screen.getByText('Ứng viên')).toBeInTheDocument()
    expect(screen.getByText('Nhà tuyển dụng')).toBeInTheDocument()
    expect(screen.getByText('Quản trị viên')).toBeInTheDocument()
    expect(screen.getByText('Công ty')).toBeInTheDocument()
    expect(screen.getByText('Tin tuyển dụng')).toBeInTheDocument()
    expect(screen.getByText('Đơn ứng tuyển')).toBeInTheDocument()
  })

  it('renders the stat values', () => {
    render(<StatsOverviewCard stats={mockStats} />)
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('20')).toBeInTheDocument()
  })

  it('renders zero values when stats are empty', () => {
    const emptyStats: AdminStats = {
      total_users: 0,
      total_candidates: 0,
      total_recruiters: 0,
      total_admins: 0,
      total_companies: 0,
      total_jobs: 0,
      total_applications: 0,
      applications_by_status: {
        applied: 0,
        under_review: 0,
        shortlisted: 0,
        interviewing: 0,
        accepted: 0,
        rejected: 0,
        withdrawn: 0,
      },
    }
    render(<StatsOverviewCard stats={emptyStats} />)
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(7)
  })
})