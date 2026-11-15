import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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

function renderPage(initialEntries = ['/recruiter/candidates/search']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <SemanticCandidateSearchPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  mockedSearchCandidates.mockResolvedValue(mockResults)
})

describe('SemanticCandidateSearchPage', () => {
  it('renders the page title', () => {
    renderPage()

    expect(
      screen.getByRole('heading', { name: /Tìm kiếm ứng viên ngữ nghĩa/i }),
    ).toBeInTheDocument()
  })

  it('searches candidates with the typed query and session ID', async () => {
    renderPage()

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react developer' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(mockedSearchCandidates).toHaveBeenCalledWith(
        { q: 'react developer' },
        expect.any(String),
      )
    })
  })

  it('renders candidate search results', async () => {
    renderPage()

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

    renderPage()

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

  it('shows error on failure and retrying reuses session ID', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 502, data: { detail: 'Search failed' } },
    })
    mockedSearchCandidates.mockRejectedValueOnce(error).mockResolvedValueOnce(mockResults)

    renderPage()

    fireEvent.change(screen.getByLabelText('Từ khóa tìm kiếm ngữ nghĩa'), {
      target: { value: 'react' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Tìm kiếm/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    const firstCallSessionId = mockedSearchCandidates.mock.calls[0][1]
    expect(firstCallSessionId).toBeTruthy()

    // Click retry button in SemanticSearchBar
    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedSearchCandidates).toHaveBeenCalledTimes(2)
      expect(screen.getByText('Nguyễn Văn A')).toBeInTheDocument()
    })

    const retryCallSessionId = mockedSearchCandidates.mock.calls[1][1]
    expect(retryCallSessionId).toBe(firstCallSessionId)
  })
})
