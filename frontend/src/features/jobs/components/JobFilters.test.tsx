import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { JobFilters } from './JobFilters'
import type { JobFiltersState } from '@/features/jobs/hooks/useJobs'

const emptyFilters: JobFiltersState = {
  keyword: '',
  workplace_type: '',
  job_type: '',
  location: '',
}

describe('JobFilters', () => {
  it('renders keyword input', () => {
    render(
      <JobFilters
        filters={emptyFilters}
        onKeywordChange={vi.fn()}
        onWorkplaceTypeChange={vi.fn()}
        onJobTypeChange={vi.fn()}
        onLocationChange={vi.fn()}
      />,
    )
    expect(screen.getByLabelText('Keyword')).toBeInTheDocument()
  })

  it('renders workplace type select with options', () => {
    render(
      <JobFilters
        filters={emptyFilters}
        onKeywordChange={vi.fn()}
        onWorkplaceTypeChange={vi.fn()}
        onJobTypeChange={vi.fn()}
        onLocationChange={vi.fn()}
      />,
    )
    const select = screen.getByLabelText('Workplace type')
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'On-site' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Hybrid' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Remote' })).toBeInTheDocument()
  })

  it('renders job type select with options', () => {
    render(
      <JobFilters
        filters={emptyFilters}
        onKeywordChange={vi.fn()}
        onWorkplaceTypeChange={vi.fn()}
        onJobTypeChange={vi.fn()}
        onLocationChange={vi.fn()}
      />,
    )
    const select = screen.getByLabelText('Job type')
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Full time' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Internship' })).toBeInTheDocument()
  })

  it('calls keyword callback on input change', () => {
    const onKeywordChange = vi.fn()
    render(
      <JobFilters
        filters={emptyFilters}
        onKeywordChange={onKeywordChange}
        onWorkplaceTypeChange={vi.fn()}
        onJobTypeChange={vi.fn()}
        onLocationChange={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByLabelText('Keyword'), {
      target: { value: 'react' },
    })
    expect(onKeywordChange).toHaveBeenCalledWith('react')
  })

  it('calls workplace type callback on select change', () => {
    const onWorkplaceTypeChange = vi.fn()
    render(
      <JobFilters
        filters={emptyFilters}
        onKeywordChange={vi.fn()}
        onWorkplaceTypeChange={onWorkplaceTypeChange}
        onJobTypeChange={vi.fn()}
        onLocationChange={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByLabelText('Workplace type'), {
      target: { value: 'remote' },
    })
    expect(onWorkplaceTypeChange).toHaveBeenCalledWith('remote')
  })

  it('calls job type callback on select change', () => {
    const onJobTypeChange = vi.fn()
    render(
      <JobFilters
        filters={emptyFilters}
        onKeywordChange={vi.fn()}
        onWorkplaceTypeChange={vi.fn()}
        onJobTypeChange={onJobTypeChange}
        onLocationChange={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByLabelText('Job type'), {
      target: { value: 'contract' },
    })
    expect(onJobTypeChange).toHaveBeenCalledWith('contract')
  })

  it('calls location callback on input change', () => {
    const onLocationChange = vi.fn()
    render(
      <JobFilters
        filters={emptyFilters}
        onKeywordChange={vi.fn()}
        onWorkplaceTypeChange={vi.fn()}
        onJobTypeChange={vi.fn()}
        onLocationChange={onLocationChange}
      />,
    )
    fireEvent.change(screen.getByLabelText('Location'), {
      target: { value: 'Hanoi' },
    })
    expect(onLocationChange).toHaveBeenCalledWith('Hanoi')
  })
})