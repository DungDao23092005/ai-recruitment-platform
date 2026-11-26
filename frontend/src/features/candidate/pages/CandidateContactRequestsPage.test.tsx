import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { CandidateContactRequestsPage } from './CandidateContactRequestsPage'
import {
  acceptContactRequest,
  declineContactRequest,
  getCandidateIncomingContactRequests,
  revokeContactAuthorization,
} from '@/api/contactRequests'
import type { CandidateContactRequestRead } from '@/types/ai'

vi.mock('@/api/contactRequests', () => ({
  acceptContactRequest: vi.fn(),
  declineContactRequest: vi.fn(),
  getCandidateIncomingContactRequests: vi.fn(),
  revokeContactAuthorization: vi.fn(),
}))

const mockedGetRequests = vi.mocked(getCandidateIncomingContactRequests)
const mockedAccept = vi.mocked(acceptContactRequest)
const mockedDecline = vi.mocked(declineContactRequest)
const mockedRevoke = vi.mocked(revokeContactAuthorization)

const mockRequests: CandidateContactRequestRead[] = [
  {
    id: 'req-1',
    company_id: 'comp-1',
    candidate_id: 'cand-1',
    requester_user_id: 'user-recruiter-1',
    status: 'pending',
    created_at: '2026-11-25T10:00:00Z',
    updated_at: '2026-11-25T10:00:00Z',
    expires_at: '2026-12-09T10:00:00Z',
    responded_at: null,
    revoked_at: null,
    company_name: 'Tech Unicorn Vietnam',
    candidate_name: 'Candidate A',
    candidate_title: 'Full Stack Dev',
  },
  {
    id: 'req-2',
    company_id: 'comp-2',
    candidate_id: 'cand-1',
    requester_user_id: 'user-recruiter-2',
    status: 'accepted',
    created_at: '2026-11-20T10:00:00Z',
    updated_at: '2026-11-21T10:00:00Z',
    expires_at: '2026-12-04T10:00:00Z',
    responded_at: '2026-11-21T10:00:00Z',
    revoked_at: null,
    company_name: 'Global AI Labs',
    candidate_name: 'Candidate A',
    candidate_title: 'Full Stack Dev',
  },
]

function renderPage(initialEntries = ['/candidate/contact-requests']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <CandidateContactRequestsPage />
    </MemoryRouter>,
  )
}

describe('CandidateContactRequestsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
  })

  it('renders list of incoming contact requests on mount', async () => {
    mockedGetRequests.mockResolvedValue(mockRequests)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Tech Unicorn Vietnam')).toBeInTheDocument()
      expect(screen.getByText('Global AI Labs')).toBeInTheDocument()
    })

    expect(screen.getAllByText('Chờ phản hồi').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Đã chấp nhận').length).toBeGreaterThanOrEqual(2)
  })

  it('renders empty state when no requests found', async () => {
    mockedGetRequests.mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Chưa có yêu cầu kết nối nào'),
      ).toBeInTheDocument()
    })
  })

  it('accepts a pending contact request', async () => {
    mockedGetRequests.mockResolvedValue(mockRequests)
    mockedAccept.mockResolvedValue({
      ...mockRequests[0],
      status: 'accepted',
      responded_at: new Date().toISOString(),
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Tech Unicorn Vietnam')).toBeInTheDocument()
    })

    const acceptButton = screen.getByRole('button', { name: /^Chấp nhận$/i })
    fireEvent.click(acceptButton)

    await waitFor(() => {
      expect(mockedAccept).toHaveBeenCalledWith('req-1')
      expect(
        screen.getByText('Đã chấp nhận yêu cầu kết nối thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('declines a pending contact request', async () => {
    mockedGetRequests.mockResolvedValue(mockRequests)
    mockedDecline.mockResolvedValue({
      ...mockRequests[0],
      status: 'declined',
      responded_at: new Date().toISOString(),
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Tech Unicorn Vietnam')).toBeInTheDocument()
    })

    const declineButton = screen.getByRole('button', { name: /^Từ chối$/i })
    fireEvent.click(declineButton)

    await waitFor(() => {
      expect(mockedDecline).toHaveBeenCalledWith('req-1')
      expect(
        screen.getByText('Đã từ chối yêu cầu kết nối.'),
      ).toBeInTheDocument()
    })
  })

  it('revokes an accepted contact authorization', async () => {
    mockedGetRequests.mockResolvedValue(mockRequests)
    mockedRevoke.mockResolvedValue({
      ...mockRequests[1],
      status: 'revoked',
      revoked_at: new Date().toISOString(),
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Global AI Labs')).toBeInTheDocument()
    })

    const revokeButton = screen.getByRole('button', { name: /Thu hồi quyền/i })
    fireEvent.click(revokeButton)

    await waitFor(() => {
      expect(mockedRevoke).toHaveBeenCalledWith('req-2')
      expect(
        screen.getByText('Đã thu hồi quyền xem thông tin liên hệ thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('switches filter tab and queries with filter', async () => {
    mockedGetRequests.mockResolvedValue(mockRequests)

    renderPage()

    await waitFor(() => {
      expect(mockedGetRequests).toHaveBeenCalledWith(undefined)
    })

    const pendingTab = screen.getByRole('button', { name: 'Chờ phản hồi' })
    fireEvent.click(pendingTab)

    await waitFor(() => {
      expect(mockedGetRequests).toHaveBeenCalledWith('pending')
    })
  })

  it('highlights target contact request card when id query parameter matches', async () => {
    mockedGetRequests.mockResolvedValue(mockRequests)

    renderPage(['/candidate/contact-requests?id=req-1'])

    await waitFor(() => {
      expect(screen.getByText('Tech Unicorn Vietnam')).toBeInTheDocument()
    })

    const targetCard = screen.getByTestId('target-contact-request-card')
    expect(targetCard).toBeInTheDocument()
    expect(targetCard).toHaveAttribute('id', 'contact-request-req-1')
    expect(targetCard).toHaveClass('ring-2', 'ring-primary', 'border-primary', 'bg-primary/5')
  })

  it('refreshes requests list when contact_request:updated event is dispatched', async () => {
    mockedGetRequests.mockResolvedValue(mockRequests)

    renderPage()

    await waitFor(() => {
      expect(mockedGetRequests).toHaveBeenCalledTimes(1)
      expect(mockedGetRequests).toHaveBeenCalledWith(undefined)
    })

    fireEvent(
      window,
      new CustomEvent('contact_request:updated', {
        detail: { entity_id: 'req-1', entity_type: 'contact_request' },
      }),
    )

    await waitFor(() => {
      expect(mockedGetRequests).toHaveBeenCalledTimes(2)
      expect(mockedGetRequests).toHaveBeenLastCalledWith(undefined)
    })
  })

  it('preserves active filter tab when contact_request:updated triggers refresh', async () => {
    mockedGetRequests.mockResolvedValue(mockRequests)

    renderPage()

    await waitFor(() => {
      expect(mockedGetRequests).toHaveBeenCalledTimes(1)
    })

    // Switch to pending tab
    const pendingTab = screen.getByRole('button', { name: 'Chờ phản hồi' })
    fireEvent.click(pendingTab)

    await waitFor(() => {
      expect(mockedGetRequests).toHaveBeenCalledWith('pending')
      expect(mockedGetRequests).toHaveBeenCalledTimes(2)
    })

    // Dispatch event
    fireEvent(
      window,
      new CustomEvent('contact_request:updated', {
        detail: { entity_id: 'req-1', entity_type: 'contact_request' },
      }),
    )

    await waitFor(() => {
      expect(mockedGetRequests).toHaveBeenCalledTimes(3)
      expect(mockedGetRequests).toHaveBeenLastCalledWith('pending')
    })
  })
})
