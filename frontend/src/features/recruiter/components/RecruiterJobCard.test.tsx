import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { RecruiterJobCard } from './RecruiterJobCard'
import apiClient from '@/api/client'
import type { Job } from '@/types/job'

vi.mock('@/api/client', () => ({
  default: {
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockedPatch = vi.mocked(apiClient.patch)
const mockedDelete = vi.mocked(apiClient.delete)

beforeEach(() => {
  vi.clearAllMocks()
})

const mockJob: Job = {
  id: 'job-1',
  company_id: '00000000-0000-0000-0000-000000000001',
  company_name: 'TechNova AI',
  title: 'Backend Engineer',
  description: 'Build robust APIs',
  status: 'draft',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

describe('RecruiterJobCard', () => {
  it('renders the job title', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={mockJob} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
  })

  it('renders company name', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={mockJob} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Công ty: TechNova AI')).toBeInTheDocument()
  })

  it('falls back to company id prefix when company_name is null', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={{ ...mockJob, company_name: null }} />
      </MemoryRouter>,
    )
    expect(screen.getByText(/Công ty: 00000000/)).toBeInTheDocument()
  })

  it('links to the edit page for the job', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={mockJob} />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('link', { name: /Sửa/i }),
    ).toHaveAttribute('href', '/recruiter/jobs/job-1/edit')
  })

  it('offers publish action for a draft job', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={mockJob} />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('button', { name: /Đăng tin/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Đóng tin/i }),
    ).not.toBeInTheDocument()
  })

  it('offers close action for a published job', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={{ ...mockJob, status: 'published' }} />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('button', { name: /Đóng tin/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Đăng tin/i }),
    ).not.toBeInTheDocument()
  })

  it('offers reopen action for a closed job', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={{ ...mockJob, status: 'closed' }} />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('button', { name: /Mở lại/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Đăng tin/i }),
    ).not.toBeInTheDocument()
  })

  it('shows no status action for an expired job', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={{ ...mockJob, status: 'expired' }} />
      </MemoryRouter>,
    )
    expect(
      screen.queryByRole('button', { name: /Đăng tin|Mở lại|Đóng tin/i }),
    ).not.toBeInTheDocument()
  })

  it('publishes a draft job directly and notifies onMutated', async () => {
    mockedPatch.mockResolvedValue({ ...mockJob, status: 'published' } as never)
    const onMutated = vi.fn()

    render(
      <MemoryRouter>
        <RecruiterJobCard job={mockJob} onMutated={onMutated} />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /Đăng tin/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith(
        '/jobs/mine/job-1/status',
        { status: 'published' },
      )
      expect(onMutated).toHaveBeenCalled()
    })
  })

  it('requires confirmation before closing a published job', async () => {
    mockedPatch.mockResolvedValue({ ...mockJob, status: 'closed' } as never)
    const onMutated = vi.fn()

    render(
      <MemoryRouter>
        <RecruiterJobCard
          job={{ ...mockJob, status: 'published' }}
          onMutated={onMutated}
        />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /Đóng tin/i }))

    const dialog = screen.getByRole('dialog')
    expect(
      within(dialog).getByText('Đóng tin tuyển dụng'),
    ).toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Đóng tin' }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith(
        '/jobs/mine/job-1/status',
        { status: 'closed' },
      )
      expect(onMutated).toHaveBeenCalled()
    })
  })

  it('requires confirmation before deleting a job', async () => {
    mockedDelete.mockResolvedValue(undefined as never)
    const onMutated = vi.fn()

    render(
      <MemoryRouter>
        <RecruiterJobCard job={mockJob} onMutated={onMutated} />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /Xóa/i }))

    const dialog = screen.getByRole('dialog')
    expect(
      within(dialog).getByText('Xóa tin tuyển dụng'),
    ).toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Xóa tin' }))

    await waitFor(() => {
      expect(mockedDelete).toHaveBeenCalledWith('/jobs/mine/job-1')
      expect(onMutated).toHaveBeenCalled()
    })
  })

  it('cancelling the delete modal does not call the API', () => {
    render(
      <MemoryRouter>
        <RecruiterJobCard job={mockJob} />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /Xóa/i }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Hủy' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mockedDelete).not.toHaveBeenCalled()
  })
})