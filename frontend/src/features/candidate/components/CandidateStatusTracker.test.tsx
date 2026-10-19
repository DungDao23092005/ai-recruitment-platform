import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CandidateStatusTracker } from './CandidateStatusTracker'
import type { ApplicationStatus } from '@/types/application'

function renderTracker(status: ApplicationStatus) {
  return render(<CandidateStatusTracker status={status} />)
}

describe('CandidateStatusTracker', () => {
  it('exposes an accessible progress group', () => {
    renderTracker('applied')

    expect(
      screen.getByRole('group', { name: 'Tiến trình ứng tuyển' }),
    ).toBeInTheDocument()
  })

  it('renders the five pipeline steps', () => {
    renderTracker('applied')

    expect(screen.getByText('Nộp hồ sơ')).toBeInTheDocument()
    expect(screen.getByText('Xem xét hồ sơ')).toBeInTheDocument()
    expect(screen.getByText('Phỏng vấn')).toBeInTheDocument()
    expect(screen.getByText('Đề nghị nhận việc')).toBeInTheDocument()
    expect(screen.getByText('Kết quả')).toBeInTheDocument()
  })

  it('marks the current step with aria-current', () => {
    renderTracker('under_review')

    const steps = screen.getAllByRole('listitem')
    expect(steps).toHaveLength(5)
    expect(steps[1]).toHaveAttribute('aria-current', 'step')
    expect(steps[0]).not.toHaveAttribute('aria-current')
  })

  it('marks earlier stages completed and later stages upcoming', () => {
    renderTracker('interviewing')

    expect(screen.getAllByText('Đã hoàn thành')).toHaveLength(2)
    expect(screen.getAllByText('Chưa bắt đầu')).toHaveLength(2)
    expect(screen.getByText('Bước hiện tại')).toBeInTheDocument()
  })

  it.each(['under_review', 'shortlisted'] as ApplicationStatus[])(
    'maps %s to the review stage',
    (status) => {
      renderTracker(status)

      const steps = screen.getAllByRole('listitem')
      expect(steps[1]).toHaveAttribute('aria-current', 'step')
    },
  )

  it('highlights the offer step when offered', () => {
    renderTracker('offered')

    const steps = screen.getAllByRole('listitem')
    expect(steps[3]).toHaveAttribute('aria-current', 'step')
    expect(screen.getAllByText('Đã hoàn thành')).toHaveLength(3)
  })

  it.each([
    ['accepted', 'Đã chấp nhận'],
    ['rejected', 'Từ chối'],
    ['withdrawn', 'Đã rút đơn'],
  ] as [ApplicationStatus, string][])(
    'shows a distinct truthful outcome for %s',
    (status, label) => {
      renderTracker(status)

      const steps = screen.getAllByRole('listitem')
      expect(steps[4]).toHaveAttribute('aria-current', 'step')
      expect(screen.getByText(label)).toBeInTheDocument()
    },
  )

  it('does not claim earlier stages were completed for terminal outcomes', () => {
    renderTracker('rejected')

    expect(screen.queryByText('Đã hoàn thành')).not.toBeInTheDocument()
  })
})
