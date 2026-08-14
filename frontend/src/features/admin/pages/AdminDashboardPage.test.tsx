import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AdminDashboardPage } from './AdminDashboardPage'
import * as adminApi from '@/api/admin'
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

vi.mock('@/api/admin', () => ({
  getAdminStats: vi.fn(),
  getSystemHealth: vi.fn(),
}))

const mockedGetAdminStats = vi.mocked(adminApi.getAdminStats)
const mockedGetSystemHealth = vi.mocked(adminApi.getSystemHealth)

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminDashboardPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AdminDashboardPage', () => {
  it('fetches stats and health on mount', async () => {
    mockedGetAdminStats.mockResolvedValue(mockStats)
    mockedGetSystemHealth.mockResolvedValue({
      status: 'healthy',
      service: 'Backend',
      version: '1.0.0',
      environment: 'dev',
    })

    renderPage()

    await waitFor(() => {
      expect(mockedGetAdminStats).toHaveBeenCalledTimes(1)
      expect(mockedGetSystemHealth).toHaveBeenCalledTimes(1)
    })
  })

  it('renders the stats overview', async () => {
    mockedGetAdminStats.mockResolvedValue(mockStats)
    mockedGetSystemHealth.mockResolvedValue({
      status: 'healthy',
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Tổng quan hệ thống')).toBeInTheDocument()
      expect(screen.getByText('10')).toBeInTheDocument()
      expect(screen.getByText('20')).toBeInTheDocument()
    })
  })

  it('renders the application status chart', async () => {
    mockedGetAdminStats.mockResolvedValue(mockStats)
    mockedGetSystemHealth.mockResolvedValue({ status: 'healthy' })

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Đơn ứng tuyển theo trạng thái'),
      ).toBeInTheDocument()
      expect(screen.getByText('5 (25%)')).toBeInTheDocument()
    })
  })

  it('renders healthy system health card', async () => {
    mockedGetAdminStats.mockResolvedValue(mockStats)
    mockedGetSystemHealth.mockResolvedValue({
      status: 'healthy',
      service: 'AI Recruitment Platform API',
      version: '1.0.0',
      environment: 'development',
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Healthy')).toBeInTheDocument()
      expect(
        screen.getByText('AI Recruitment Platform API'),
      ).toBeInTheDocument()
    })
  })

  it('shows an error state with retry', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetAdminStats
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(mockStats)
    mockedGetSystemHealth.mockResolvedValue({ status: 'healthy' })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('Tổng quan hệ thống')).toBeInTheDocument()
    })
  })

  it('shows unhealthy health card when health fails', async () => {
    mockedGetAdminStats.mockResolvedValue(mockStats)
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetSystemHealth.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Unreachable')).toBeInTheDocument()
    })
  })
})