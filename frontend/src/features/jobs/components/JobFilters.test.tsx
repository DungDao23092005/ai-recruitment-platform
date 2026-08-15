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
    expect(screen.getByLabelText('Từ khóa')).toBeInTheDocument()
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
    const select = screen.getByLabelText('Hình thức làm việc')
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Tại văn phòng' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Hybrid' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Từ xa' })).toBeInTheDocument()
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
    const select = screen.getByLabelText('Loại công việc')
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Toàn thời gian' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Thực tập sinh' })).toBeInTheDocument()
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
    fireEvent.change(screen.getByLabelText('Từ khóa'), {
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
    fireEvent.change(screen.getByLabelText('Hình thức làm việc'), {
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
    fireEvent.change(screen.getByLabelText('Loại công việc'), {
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
    fireEvent.change(screen.getByLabelText('Địa điểm'), {
      target: { value: 'Hanoi' },
    })
    expect(onLocationChange).toHaveBeenCalledWith('Hanoi')
  })
})