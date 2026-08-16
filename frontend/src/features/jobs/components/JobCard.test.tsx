import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { JobCard } from './JobCard'
import type { Job } from '@/types/job'

const mockJob: Job = {
  id: 'job-1',
  company_id: '00000000-0000-0000-0000-000000000001',
  company_name: 'TechNova AI',
  title: 'Senior Frontend Engineer',
  description: 'Build modern web applications with React.',
  status: 'published',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Ho Chi Minh City',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

describe('JobCard', () => {
  it('renders the job title', () => {
    render(
      <MemoryRouter>
        <JobCard job={mockJob} />
      </MemoryRouter>,
    )
    expect(
      screen.getByText('Senior Frontend Engineer'),
    ).toBeInTheDocument()
  })

  it('renders company name', () => {
    render(
      <MemoryRouter>
        <JobCard job={mockJob} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Công ty TechNova AI')).toBeInTheDocument()
  })

  it('falls back to company id prefix when company_name is null', () => {
    render(
      <MemoryRouter>
        <JobCard job={{ ...mockJob, company_name: null }} />
      </MemoryRouter>,
    )
    expect(screen.getByText(/Công ty 00000000/)).toBeInTheDocument()
  })

  it('renders location', () => {
    render(
      <MemoryRouter>
        <JobCard job={mockJob} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Ho Chi Minh City')).toBeInTheDocument()
  })

  it('renders job type and workplace type badges', () => {
    render(
      <MemoryRouter>
        <JobCard job={mockJob} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Toàn thời gian')).toBeInTheDocument()
    expect(screen.getByText('Từ xa')).toBeInTheDocument()
  })

  it('renders a link to the job detail page', () => {
    render(
      <MemoryRouter>
        <JobCard job={mockJob} />
      </MemoryRouter>,
    )
    const link = screen.getByRole('link', { name: /Xem chi tiết/i })
    expect(link).toHaveAttribute('href', '/jobs/job-1')
  })

  it('creates the correct href per job.id for two different jobs', () => {
    const jobA: Job = { ...mockJob, id: 'job-a', title: 'Job A' }
    const jobB: Job = { ...mockJob, id: 'job-b', title: 'Job B' }

    render(
      <MemoryRouter>
        <JobCard job={jobA} />
        <JobCard job={jobB} />
      </MemoryRouter>,
    )

    const links = screen.getAllByRole('link', { name: /Xem chi tiết/i })
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAttribute('href', '/jobs/job-a')
    expect(links[1]).toHaveAttribute('href', '/jobs/job-b')
  })
})