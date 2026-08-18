import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StatusUpdateModal } from './StatusUpdateModal'
import type { Application, ApplicationStatus } from '@/types/application'

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

function renderModal(status: ApplicationStatus) {
  return render(
    <StatusUpdateModal
      application={{ ...baseApplication, status }}
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

    expect(selectOptions()).toEqual(['under_review'])
  })

  it('only contains valid transitions for an interviewing application', () => {
    renderModal('interviewing')

    expect(selectOptions()).toEqual(['accepted', 'rejected'])
  })

  it('shows a notice for terminal states with no further transitions', () => {
    renderModal('accepted')

    expect(screen.queryByLabelText('Trạng thái')).not.toBeInTheDocument()
    expect(
      screen.getByText(/không còn trạng thái tuyển dụng nào/),
    ).toBeInTheDocument()
  })
})