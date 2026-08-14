import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { SemanticJobSearchPage } from './SemanticJobSearchPage'
import { searchJobs } from '@/api/ai'
import type { SemanticSearchResult } from '@/types/ai'

const mockResults: SemanticSearchResult[] = [
  {
    id: 'job-1',
    score: 0.87,
    skills: ['Python', 'FastAPI'],
    created_at: '2026-01-01T00:00:00+00:00',
  },
]

vi.mock('@/api/ai', () => ({
  searchJobs: vi.fn(),
}))

const mockedSearchJobs = vi.mocked(searchJobs)

beforeEach(() => {
  vi.resetAllMocks()
  mockedSearchJobs.mockResolvedValue(mockResults)
})

describe('SemanticJobSearchPage', () => {
  it('renders the page title', () => {
    render(<SemanticJobSearchPage />)

    expect(
      screen.getByRole('heading', { name: /Tìm kiếm việc làm ngữ nghĩa/i }),
    ).toBeInTheDocument()
  })

  it('searches jobs with the typed query', async () => {
    render(<SemanticJobSearchPage />)

    fireEvent.change(screen.getByLabelText('Semantic search query'), {
      target: { value: 'python backend' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(mockedSearchJobs).toHaveBeenCalledWith({
        q: 'python backend',
      })
    })
  })

  it('renders job search results', async () => {
    render(<SemanticJobSearchPage />)

    fireEvent.change(screen.getByLabelText('Semantic search query'), {
      target: { value: 'python' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByText('job-1')).toBeInTheDocument()
      expect(screen.getByText('Python')).toBeInTheDocument()
    })
  })

  it('shows error when search fails', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 502, data: { detail: 'Search failed' } },
    })
    mockedSearchJobs.mockRejectedValue(error)

    render(<SemanticJobSearchPage />)

    fireEvent.change(screen.getByLabelText('Semantic search query'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('retries after failure', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 502, data: { detail: 'Search failed' } },
    })
    mockedSearchJobs
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(mockResults)

    render(<SemanticJobSearchPage />)

    fireEvent.change(screen.getByLabelText('Semantic search query'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('job-1')).toBeInTheDocument()
    })
  })
})