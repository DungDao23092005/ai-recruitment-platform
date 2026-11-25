import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { CandidatePreviewModal } from './CandidatePreviewModal'
import {
  createContactRequest,
  getCandidateContactDetails,
  getCandidatePreview,
} from '@/api/contactRequests'
import type {
  CandidateContactResponse,
  CandidatePreviewResponse,
} from '@/types/ai'

vi.mock('@/api/contactRequests', () => ({
  createContactRequest: vi.fn(),
  getCandidateContactDetails: vi.fn(),
  getCandidatePreview: vi.fn(),
}))

const mockedGetPreview = vi.mocked(getCandidatePreview)
const mockedCreateRequest = vi.mocked(createContactRequest)
const mockedGetContact = vi.mocked(getCandidateContactDetails)

const candidateId = 'cand-123'

const mockPreviewData: CandidatePreviewResponse = {
  id: candidateId,
  full_name: 'Nguyen Van A',
  title: 'Senior Python Developer',
  summary: 'Passionate backend developer with 5 years experience',
  total_years_experience: 5,
  skills: ['Python', 'FastAPI', 'Docker', 'PostgreSQL'],
  experiences: [
    {
      company: 'Tech Solutions',
      position: 'Backend Lead',
      start_date: '2021-01',
      end_date: null,
      is_current: true,
      description: 'Microservices architecture with FastAPI',
      skills_used: ['Python', 'FastAPI'],
    },
  ],
  education: [
    {
      institution: 'University of Engineering',
      degree: 'Bachelor',
      field_of_study: 'Computer Science',
      start_year: 2016,
      end_year: 2020,
    },
  ],
  contact_request_status: null,
  contact_request_id: null,
  can_request_contact: true,
  cooldown_until: null,
}

describe('CandidatePreviewModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders masked candidate preview without email or phone', async () => {
    mockedGetPreview.mockResolvedValue(mockPreviewData)

    render(<CandidatePreviewModal candidateId={candidateId} onClose={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Nguyen Van A')).toBeInTheDocument()
      expect(screen.getByText('Senior Python Developer')).toBeInTheDocument()
      expect(screen.getByText('5 năm kinh nghiệm')).toBeInTheDocument()
      expect(screen.getByText('Tech Solutions')).toBeInTheDocument()
    })

    // Strict PII invariant: Email and Phone are never rendered in initial preview
    expect(screen.queryByText(/@/)).not.toBeInTheDocument()
    expect(screen.queryByText(/09\d{8}/)).not.toBeInTheDocument()

    // Send request button is enabled
    expect(
      screen.getByRole('button', { name: /Gửi yêu cầu kết nối/i }),
    ).toBeEnabled()
  })

  it('sends contact request successfully', async () => {
    mockedGetPreview.mockResolvedValue(mockPreviewData)
    mockedCreateRequest.mockResolvedValue({
      id: 'req-1',
      company_id: 'comp-1',
      candidate_id: candidateId,
      requester_user_id: 'user-1',
      status: 'pending',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      responded_at: null,
      revoked_at: null,
      company_name: 'Test Corp',
      candidate_name: 'Nguyen Van A',
      candidate_title: 'Senior Python Developer',
    })

    render(<CandidatePreviewModal candidateId={candidateId} onClose={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Gửi yêu cầu kết nối/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Gửi yêu cầu kết nối/i }))

    await waitFor(() => {
      expect(mockedCreateRequest).toHaveBeenCalledWith(candidateId)
      expect(
        screen.getByText('Đã gửi yêu cầu kết nối tới ứng viên thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('renders pending state when contact request is already pending', async () => {
    mockedGetPreview.mockResolvedValue({
      ...mockPreviewData,
      contact_request_status: 'pending',
      can_request_contact: false,
    })

    render(<CandidatePreviewModal candidateId={candidateId} onClose={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Đang chờ phản hồi')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Đang chờ ứng viên phản hồi/i }),
      ).toBeDisabled()
    })
  })

  it('allows revealing authorized contact details when status is accepted', async () => {
    mockedGetPreview.mockResolvedValue({
      ...mockPreviewData,
      contact_request_status: 'accepted',
      can_request_contact: false,
    })
    mockedGetContact.mockResolvedValue({
      candidate_id: candidateId,
      full_name: 'Nguyen Van A',
      email: 'nguyen.a@example.com',
      phone: '0987654321',
      disclosed_at: '2026-11-25T10:00:00Z',
    })

    render(<CandidatePreviewModal candidateId={candidateId} onClose={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Đã được cấp quyền')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Xem thông tin liên hệ/i }),
      ).toBeEnabled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Xem thông tin liên hệ/i }))

    await waitFor(() => {
      expect(mockedGetContact).toHaveBeenCalledWith(candidateId)
      expect(screen.getByText('nguyen.a@example.com')).toBeInTheDocument()
      expect(screen.getByText('0987654321')).toBeInTheDocument()
      expect(screen.getByText(/Thông tin liên hệ chính thức/i)).toBeInTheDocument()
    })
  })

  it('shows cooldown message when candidate declined and can_request_contact is false', async () => {
    mockedGetPreview.mockResolvedValue({
      ...mockPreviewData,
      contact_request_status: 'declined',
      can_request_contact: false,
    })

    render(<CandidatePreviewModal candidateId={candidateId} onClose={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Đã từ chối')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Chưa thể gửi yêu cầu/i }),
      ).toBeDisabled()
      expect(
        screen.getByText(/Thời gian chờ 30 ngày sau khi bị từ chối/i),
      ).toBeInTheDocument()
    })
  })
})
