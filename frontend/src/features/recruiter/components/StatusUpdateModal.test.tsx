import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StatusUpdateModal } from './StatusUpdateModal'
import type {
  Application,
  ApplicationStatus,
  Interview,
  InterviewStatus,
} from '@/types/application'

vi.mock('@/api/client', () => ({
  default: {
    patch: vi.fn(),
  },
}))

const baseApplication: Application = {
  id: 'app-1',
  candidate_id: '11111111-1111-1111-1111-111111111111',
  job_id: 'job-1',
  status: 'applied',
  created_at: '2026-01-20T00:00:00Z',
  updated_at: '2026-01-20T00:00:00Z',
  candidate: null,
}

function makeInterview(status: InterviewStatus): Interview {
  return {
    id: `interview-${status}`,
    application_id: 'app-1',
    scheduled_at: '2026-08-20T10:00:00Z',
    duration_minutes: 60,
    interview_type: 'technical',
    meeting_url: null,
    location: null,
    notes: null,
    candidate_notes: null,
    status,
    created_at: '2026-08-18T00:00:00Z',
    updated_at: '2026-08-18T00:00:00Z',
  }
}

function renderModal(status: ApplicationStatus, interviews?: Interview[]) {
  return render(
    <StatusUpdateModal
      application={{ ...baseApplication, status }}
      interviews={interviews}
      onClose={() => {}}
    />,
  )
}

function selectOptions(): string[] {
  const select = screen.getByLabelText('Trạng thái') as HTMLSelectElement
  return Array.from(select.options).map((option) => option.value)
}

describe('StatusUpdateModal', () => {
  it('does not contain WITHDRAWN in the recruiter dropdown', () => {
    renderModal('applied')

    expect(selectOptions()).not.toContain('withdrawn')
  })

  it('does not contain APPLIED as a recruiter dropdown target', () => {
    renderModal('applied')

    expect(selectOptions()).not.toContain('applied')
  })

  it('only contains valid transitions for an applied application', () => {
    renderModal('applied')

    expect(selectOptions()).toEqual(['under_review', 'rejected'])
  })

  it('only allows recruiter-owned transitions after an interview', () => {
    renderModal('interviewing', [
      makeInterview('candidate_confirmed'),
    ])

    expect(selectOptions()).toEqual([
      'under_review',
      'offered',
      'rejected',
    ])
  })

  it('removes offered when there are no interviews', () => {
    renderModal('interviewing')

    expect(selectOptions()).toEqual(['under_review', 'rejected'])
    expect(
      screen.getByText(/Chưa có buổi phỏng vấn nào/),
    ).toBeInTheDocument()
  })

  it('removes offered when an interview is still scheduled', () => {
    renderModal('interviewing', [makeInterview('scheduled')])

    expect(selectOptions()).toEqual(['under_review', 'rejected'])
    expect(
      screen.getByText(/đang chờ xác nhận/),
    ).toBeInTheDocument()
  })

  it('removes offered when every interview was declined or cancelled', () => {
    renderModal('interviewing', [
      makeInterview('candidate_declined'),
      makeInterview('cancelled'),
    ])

    expect(selectOptions()).toEqual(['under_review', 'rejected'])
    expect(
      screen.getByText(/Cần ít nhất một buổi phỏng vấn/),
    ).toBeInTheDocument()
  })

  it('removes offered when a confirmed interview still has a pending one', () => {
    renderModal('interviewing', [
      makeInterview('candidate_confirmed'),
      makeInterview('scheduled'),
    ])

    expect(selectOptions()).toEqual(['under_review', 'rejected'])
    expect(
      screen.getByText(/đang chờ xác nhận/),
    ).toBeInTheDocument()
  })

  it('allows offered when a completed interview remains', () => {
    renderModal('interviewing', [makeInterview('completed')])

    expect(selectOptions()).toContain('offered')
  })

  it('only contains valid transitions for an offered application', () => {
    renderModal('offered')

    expect(screen.queryByLabelText('Trạng thái')).not.toBeInTheDocument()
    expect(
      screen.getByText(/Chỉ ứng viên có thể chấp nhận hoặc từ chối/),
    ).toBeInTheDocument()
  })

  it('does not expose statuses forbidden by the published pipeline', () => {
    renderModal('interviewing', [
      makeInterview('candidate_confirmed'),
    ])

    const options = selectOptions()
    expect(options).toContain('offered')
    ;['shortlisted', 'withdrawn', 'interviewing', 'applied', 'accepted'].forEach(
      (status) => {
        expect(options).not.toContain(status)
      },
    )
  })

  it('shows a notice for terminal states with no further transitions', () => {
    renderModal('accepted')

    expect(screen.queryByLabelText('Trạng thái')).not.toBeInTheDocument()
    expect(
      screen.getByText(/không còn trạng thái tuyển dụng nào/),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Lưu trạng thái/i }),
    ).toBeDisabled()
  })

  it('shows a notice for the offered terminal transition source', () => {
    renderModal('rejected')

    expect(screen.queryByLabelText('Trạng thái')).not.toBeInTheDocument()
    expect(
      screen.getByText(/không còn trạng thái tuyển dụng nào/),
    ).toBeInTheDocument()
  })
})