import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { SemanticCandidateSearchPage } from './SemanticCandidateSearchPage'
import { searchCandidates } from '@/api/ai'
import type { SemanticSearchResult } from '@/types/ai'

const mockResults: SemanticSearchResult[] = [
  {
    id: 'cand-1',
    score: 0.92,
    skills: ['React', 'TypeScript'],
    created_at: '2026-01-01T00:00:00+00:00',
    full_name: 'Nguyễn Văn A',
    title: 'Backend Engineer',
  },
]

vi.mock('@/api/ai', () => ({
  searchCandidates: vi.fn(),
}))

const mockedSearchCandidates = vi.mocked(searchCandidates)

beforeEach(() => {
  vi.resetAllMocks()
  mockedSearchCandidates.mockResolvedValue(mockResults)
})

describe('SemanticCandidateSearchPage', () => {
  it('renders the page title', () => {
    render(<SemanticCandidateSearchPage />)

    expect(
      screen.getByRole('heading', { name: /Tìm kiếm ứng viên ngữ nghĩa/i }),
    ).toBeInTheDocument()
  })

  it('searches candidates with the typed query', async () => {
    render(<SemanticCandidateSearchPage />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react developer' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(mockedSearchCandidates).toHaveBeenCalledWith({
        q: 'react developer',
      })
    })
  })

  it('renders candidate search results', async () => {
    render(<SemanticCandidateSearchPage />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByText('Nguyễn Văn A')).toBeInTheDocument()
      expect(screen.getByText('React')).toBeInTheDocument()
    })
  })

  it('shows empty state when no candidates', async () => {
    mockedSearchCandidates.mockResolvedValue([])

    render(<SemanticCandidateSearchPage />)

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
    mockedSearchCandidates.mockRejectedValue(error)

    render(<SemanticCandidateSearchPage />)

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })
})