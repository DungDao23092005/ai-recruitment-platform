import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { RecruiterJobCard } from './RecruiterJobCard'
import type { Job } from '@/types/job'

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
})