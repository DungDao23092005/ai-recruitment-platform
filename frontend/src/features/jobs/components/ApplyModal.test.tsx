import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ApplyModal } from './ApplyModal'
import * as applicationsApi from '@/api/applications'
import type { Job } from '@/types/job'
import type { Application } from '@/types/application'

const mockJob: Job = {
  id: 'job-1',
  company_id: '00000000-0000-0000-0000-000000000001',
  company_name: 'TechNova AI',
  title: 'Senior Frontend Engineer',
  description: 'Build modern web applications.',
  status: 'published',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

const applied: Application = {
  id: 'app-1',
  candidate_id: '11111111-1111-1111-1111-111111111111',
  job_id: 'job-1',
  status: 'applied',
  created_at: '2026-01-20T00:00:00Z',
  updated_at: '2026-01-20T00:00:00Z',
  candidate: null,
}

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
  withdrawApplication: vi.fn(),
}))

const mockedApplyJob = vi.mocked(applicationsApi.applyJob)
const mockedWithdrawApplication = vi.mocked(
  applicationsApi.withdrawApplication,
)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ApplyModal', () => {
  it('calls the withdraw endpoint when the candidate withdraws', async () => {
    mockedApplyJob.mockResolvedValue(applied as never)
    mockedWithdrawApplication.mockResolvedValue({
      ...applied,
      status: 'withdrawn',
    } as never)

    render(<ApplyModal job={mockJob} onClose={() => {}} />)

    fireEvent.click(
      screen.getByRole('button', { name: /Xác nhận ứng tuyển/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Đã nộp đơn thành công')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Rút đơn ứng tuyển/i }),
    )

    await waitFor(() => {
      expect(mockedWithdrawApplication).toHaveBeenCalledWith('app-1')
      expect(screen.getByText('Đã rút đơn ứng tuyển')).toBeInTheDocument()
    })
  })

  it('does not show the withdraw action before a successful apply', () => {
    render(<ApplyModal job={mockJob} onClose={() => {}} />)

    expect(
      screen.queryByRole('button', { name: /Rút đơn ứng tuyển/i }),
    ).not.toBeInTheDocument()
  })
})