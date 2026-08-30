import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  SemanticSearchBar,
  formatSearchScore,
} from './SemanticSearchBar'
import type { SemanticSearchResult } from '@/types/ai'

const mockResults: SemanticSearchResult[] = [
  {
    id: 'candidate-1',
    score: 0.87,
    skills: ['Python', 'FastAPI'],
    created_at: '2026-01-01T00:00:00+00:00',
    full_name: 'Nguyễn Văn A',
    title: 'Backend Engineer',
  },
]

const mockResultsWithoutName: SemanticSearchResult[] = [
  {
    id: 'candidate-2',
    score: 0.75,
    skills: ['React', 'TypeScript'],
    created_at: '2026-01-01T00:00:00+00:00',
    full_name: null,
    title: 'Frontend Developer',
    company_name: null,
    location: null,
  },
]

const mockResultsWithTitleOnly: SemanticSearchResult[] = [
  {
    id: 'job-1',
    score: 0.76,
    skills: ['Python', 'FastAPI'],
    created_at: '2026-01-01T00:00:00+00:00',
    full_name: null,
    title: 'Backend Engineer',
    company_name: 'Example Company',
    location: 'HCM',
  },
]

const mockSearchFn = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  mockSearchFn.mockResolvedValue(mockResults)
})

describe('SemanticSearchBar', () => {
  it('renders search input and button', () => {
    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    expect(
      screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Tìm kiếm/i }),
    ).toBeInTheDocument()
  })

  it('clicking search calls searchFn with the query', async () => {
    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'python backend' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(mockSearchFn).toHaveBeenCalledWith('python backend')
    })
  })

  it('pressing Enter triggers search', async () => {
    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react developer' },
    })
    fireEvent.submit(screen.getByRole('searchbox', { name: /Từ khóa/i }))

    await waitFor(() => {
      expect(mockSearchFn).toHaveBeenCalledWith('react developer')
    })
  })

  it('does not search for empty query', async () => {
    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    expect(mockSearchFn).not.toHaveBeenCalled()
  })

  it('shows loading state while searching', async () => {
    mockSearchFn.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockResults), 50)),
    )

    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByText('Đang tìm kiếm ngữ nghĩa...')).toBeInTheDocument()
    })
  })

  it('renders results with candidate full_name and title', async () => {
    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'python' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByText('Nguyễn Văn A')).toBeInTheDocument()
      // Candidate title should be shown as subtitle
      expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
      expect(screen.getByText('Python')).toBeInTheDocument()
      expect(
        screen.getByLabelText('Độ phù hợp 87%'),
      ).toBeInTheDocument()
    })
  })

  it('renders job results with title, company, and location', async () => {
    mockSearchFn.mockResolvedValue(mockResultsWithTitleOnly)

    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'python' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      // Job title should be displayed (not UUID)
      expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
      // Company and location should be displayed in subtitle
      expect(screen.getByText('Example Company • HCM')).toBeInTheDocument()
      // Score should be displayed
      expect(screen.getByText('76%')).toBeInTheDocument()
      // Skills should be displayed
      expect(screen.getByText('Python')).toBeInTheDocument()
      expect(screen.getByText('FastAPI')).toBeInTheDocument()
      // UUID should NOT be the primary display
      expect(screen.queryByText('job-1')).not.toBeInTheDocument()
    })
  })

  it('falls back to title when full_name is missing', async () => {
    mockSearchFn.mockResolvedValue(mockResultsWithoutName)

    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      // Should show title instead of UUID
      expect(screen.getByText('Frontend Developer')).toBeInTheDocument()
      // UUID should NOT be displayed
      expect(screen.queryByText('candidate-2')).not.toBeInTheDocument()
    })
  })

  it('shows empty state when no results', async () => {
    mockSearchFn.mockResolvedValue([])

    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'nothing' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Không tìm thấy kết quả phù hợp.'),
      ).toBeInTheDocument()
    })
  })

  it('shows error on failure', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 502, data: { detail: 'Search failed' } },
    })
    mockSearchFn.mockRejectedValue(error)

    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Thử lại/i }),
    ).toBeInTheDocument()
  })

  it('retries after failure', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 502, data: { detail: 'Search failed' } },
    })
    mockSearchFn
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(mockResults)

    render(<SemanticSearchBar searchFn={mockSearchFn} />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('Nguyễn Văn A')).toBeInTheDocument()
    })
    expect(mockSearchFn).toHaveBeenCalledTimes(2)
  })

  it('formats score as percentage', () => {
    expect(formatSearchScore(0.87)).toBe('87%')
    expect(formatSearchScore(0.5)).toBe('50%')
    expect(formatSearchScore(1)).toBe('100%')
    expect(formatSearchScore(Number.NaN)).toBe('0%')
  })
})
