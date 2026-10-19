import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { WithdrawConfirmModal } from './WithdrawConfirmModal'
import * as applicationsApi from '@/api/applications'
import type { ApplicationWithJob } from '@/types/application'

vi.mock('@/api/applications', () => ({
  withdrawApplication: vi.fn(),
}))

const mockedWithdrawApplication = vi.mocked(applicationsApi.withdrawApplication)

const mockApplication: ApplicationWithJob = {
  id: 'app-1',
  job_id: 'job-1',
  job_title: 'Backend Developer',
  company_name: 'ABC Technology',
  status: 'interviewing',
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
}

function renderModal(overrides: Partial<Parameters<typeof WithdrawConfirmModal>[0]> = {}) {
  const props = {
    application: mockApplication,
    onClose: vi.fn(),
    onSuccess: vi.fn(),
    onRefresh: vi.fn(),
    ...overrides,
  }
  return { props, ...render(<WithdrawConfirmModal {...props} />) }
}

describe('WithdrawConfirmModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a confirmation dialog naming the job', () => {
    renderModal()

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Xác nhận rút đơn/i }),
    ).toBeInTheDocument()
    expect(screen.getAllByText(/Backend Developer/).length).toBeGreaterThan(0)
  })

  it('withdraws and reports the updated application on success', async () => {
    const updated = {
      id: 'app-1',
      candidate_id: 'candidate-1',
      job_id: 'job-1',
      status: 'withdrawn' as const,
      created_at: '2026-08-18T00:00:00Z',
      updated_at: '2026-08-18T00:00:00Z',
      candidate: null,
    }
    mockedWithdrawApplication.mockResolvedValue(updated)
    const { props } = renderModal()

    fireEvent.click(screen.getByRole('button', { name: /Xác nhận rút đơn/i }))

    await waitFor(() => {
      expect(mockedWithdrawApplication).toHaveBeenCalledWith('app-1')
      expect(props.onSuccess).toHaveBeenCalledWith(updated)
    })
  })

  it('shows a loading state while submitting', async () => {
    mockedWithdrawApplication.mockReturnValue(new Promise(() => {}))
    renderModal()

    fireEvent.click(screen.getByRole('button', { name: /Xác nhận rút đơn/i }))

    expect(
      await screen.findByRole('button', { name: /Đang rút/i }),
    ).toBeDisabled()
  })

  it('shows a friendly error when the request fails', async () => {
    mockedWithdrawApplication.mockRejectedValue(
      Object.assign(new Error('boom'), {
        response: { status: 500, data: { detail: 'Server error' } },
      }),
    )
    const { props } = renderModal()

    fireEvent.click(screen.getByRole('button', { name: /Xác nhận rút đơn/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
    expect(props.onSuccess).not.toHaveBeenCalled()
  })

  it('refreshes and explains a concurrent update on 409', async () => {
    mockedWithdrawApplication.mockRejectedValue(
      Object.assign(new Error('conflict'), { response: { status: 409 } }),
    )
    const { props } = renderModal()

    fireEvent.click(screen.getByRole('button', { name: /Xác nhận rút đơn/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/làm mới/i)
    expect(props.onRefresh).toHaveBeenCalled()
    expect(props.onSuccess).not.toHaveBeenCalled()
    expect(
      screen.getByRole('button', { name: /Xác nhận rút đơn/i }),
    ).toBeDisabled()
  })

  it('closes without withdrawing when cancelled', () => {
    const { props } = renderModal()

    fireEvent.click(screen.getByRole('button', { name: /^Hủy$/i }))

    expect(props.onClose).toHaveBeenCalled()
    expect(mockedWithdrawApplication).not.toHaveBeenCalled()
  })
})
