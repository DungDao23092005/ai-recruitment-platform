import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { InterviewDeclineModal } from './InterviewDeclineModal'
import * as interviewsApi from '@/api/interviews'
import type { Interview } from '@/types/application'

vi.mock('@/api/interviews', () => ({
  candidateActionInterview: vi.fn(),
}))

const mockedCandidateActionInterview = vi.mocked(
  interviewsApi.candidateActionInterview,
)

const mockInterview: Interview = {
  id: 'interview-1',
  application_id: 'app-1',
  scheduled_at: '2026-08-20T10:00:00Z',
  duration_minutes: 60,
  interview_type: 'technical',
  meeting_url: null,
  location: 'Online',
  notes: null,
  candidate_notes: null,
  status: 'scheduled',
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
}

function renderModal() {
  const props = {
    applicationId: 'app-1',
    interview: mockInterview,
    onClose: vi.fn(),
    onDeclined: vi.fn(),
    onRefresh: vi.fn(),
  }
  return { props, ...render(<InterviewDeclineModal {...props} />) }
}

describe('InterviewDeclineModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a decline dialog with a required reason field', () => {
    renderModal()

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText(/Lý do từ chối/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Xác nhận từ chối/i }),
    ).toBeInTheDocument()
  })

  it('blocks submission and shows a field error when the reason is empty', async () => {
    renderModal()

    fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

    expect(
      await screen.findByText(/Vui lòng nhập lý do từ chối/i),
    ).toBeInTheDocument()
    expect(mockedCandidateActionInterview).not.toHaveBeenCalled()
  })

  it('treats a whitespace-only reason as empty', async () => {
    renderModal()

    fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

    expect(
      await screen.findByText(/Vui lòng nhập lý do từ chối/i),
    ).toBeInTheDocument()
    expect(mockedCandidateActionInterview).not.toHaveBeenCalled()
  })

  it('submits the trimmed reason and reports the updated interview', async () => {
    const updated = {
      ...mockInterview,
      status: 'candidate_declined' as const,
      candidate_notes: 'Busy that day',
    }
    mockedCandidateActionInterview.mockResolvedValue(updated)
    const { props } = renderModal()

    fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
      target: { value: '  Busy that day  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

    await waitFor(() => {
      expect(mockedCandidateActionInterview).toHaveBeenCalledWith(
        'app-1',
        'interview-1',
        'decline',
        'Busy that day',
      )
      expect(props.onDeclined).toHaveBeenCalledWith(updated)
    })
  })

  it('shows a loading state while submitting', async () => {
    mockedCandidateActionInterview.mockReturnValue(new Promise(() => {}))
    renderModal()

    fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
      target: { value: 'Busy' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

    expect(
      await screen.findByRole('button', { name: /Đang gửi/i }),
    ).toBeDisabled()
  })

  it('shows a friendly error when the request fails', async () => {
    mockedCandidateActionInterview.mockRejectedValue(
      Object.assign(new Error('boom'), {
        response: { status: 400, data: { detail: 'Không thể từ chối' } },
      }),
    )
    renderModal()

    fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
      target: { value: 'Busy' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

    expect(await screen.findByText('Không thể từ chối')).toBeInTheDocument()
  })

  it('refreshes and explains a concurrent update on 409', async () => {
    mockedCandidateActionInterview.mockRejectedValue(
      Object.assign(new Error('conflict'), { response: { status: 409 } }),
    )
    const { props } = renderModal()

    fireEvent.change(screen.getByLabelText(/Lý do từ chối/i), {
      target: { value: 'Busy' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Xác nhận từ chối/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/làm mới/i)
    expect(props.onRefresh).toHaveBeenCalled()
    expect(props.onDeclined).not.toHaveBeenCalled()
  })

  it('closes without submitting when cancelled', () => {
    const { props } = renderModal()

    fireEvent.click(screen.getByRole('button', { name: /^Hủy$/i }))

    expect(props.onClose).toHaveBeenCalled()
    expect(mockedCandidateActionInterview).not.toHaveBeenCalled()
  })
})
