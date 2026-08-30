import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ExplainMatchModal } from './ExplainMatchModal'
import { explainMatch } from '@/api/ai'
import type { ExplainMatchResponse, MatchResult } from '@/types/ai'

const mockMatchResult: MatchResult = {
  overall_score: 82,
  cosine_similarity: 0.85,
  skill_coverage_score: 0.8,
  experience_match_score: 0.75,
  matching_skills: ['React', 'TypeScript'],
  skill_gap: ['GraphQL'],
  match_reasons: ['Strong skill overlap'],
}

const mockExplanation: ExplainMatchResponse = {
  match_score: 82,
  summary: 'The candidate matches the role well.',
  strengths: ['Strong overlap in React and TypeScript'],
  missing_skills: ['GraphQL'],
  experience_analysis: 'Candidate has 5 years experience vs 4 required.',
  education_analysis: 'Candidate has relevant education.',
  evidence: [],
  recommendation: 'Proceed to interview.',
  confidence: 0.9,
}

vi.mock('@/api/ai', () => ({
  explainMatch: vi.fn(),
}))

const mockedExplainMatch = vi.mocked(explainMatch)

beforeEach(() => {
  vi.resetAllMocks()
})

describe('ExplainMatchModal', () => {
  it('renders the modal title', () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    expect(
      screen.getByRole('dialog', {
        name: /Giải Thích Chi Tiết Độ Phù Hợp Bằng AI/i,
      }),
    ).toBeInTheDocument()
  })

  it('renders loading text while fetching', () => {
    mockedExplainMatch.mockImplementation(
      () => new Promise(() => {}),
    )

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    expect(
      screen.getByText('Gemini AI đang phân tích dữ liệu đối sánh...'),
    ).toBeInTheDocument()
  })

  it('renders summary', async () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(
        screen.getByText('The candidate matches the role well.'),
      ).toBeInTheDocument()
    })
  })

  it('renders strengths', async () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(
        screen.getByText('Strong overlap in React and TypeScript'),
      ).toBeInTheDocument()
    })
  })

  it('renders skill gaps', async () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('GraphQL')).toBeInTheDocument()
    })
  })

  it('renders experience analysis', async () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(
        screen.getByText('Candidate has 5 years experience vs 4 required.'),
      ).toBeInTheDocument()
    })
  })

  it('renders recommendation', async () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(
        screen.getByText('Proceed to interview.'),
      ).toBeInTheDocument()
    })
  })

  it('calls explainMatch with match result and optional facts', async () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)

    const candidate = {
      full_name: 'John Doe',
      email: null,
      phone: null,
      title: 'Frontend Engineer',
      summary: 'React specialist with 5 years of experience.',
      total_years_experience: 5,
      skills: ['React', 'TypeScript'],
      experiences: [],
      education: [],
      certifications: [],
      languages: [],
    }
    const job = {
      title: 'Senior Frontend Engineer',
      summary: 'Build modern web applications with React.',
      required_skills: ['React', 'TypeScript', 'GraphQL'],
      preferred_skills: ['Next.js'],
      minimum_years_experience: 4,
      education_level: 'Bachelor',
    }

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        candidate={candidate}
        job={job}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(mockedExplainMatch).toHaveBeenCalledWith({
        match_result: mockMatchResult,
        candidate,
        job,
      })
    })
  })

  it('sends null for missing candidate and job', async () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(mockedExplainMatch).toHaveBeenCalledWith({
        match_result: mockMatchResult,
        candidate: null,
        job: null,
      })
    })
  })

  it('shows friendly error on failure', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 422, data: { detail: 'Invalid payload' } },
    })
    mockedExplainMatch.mockRejectedValue(error)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Thử lại/i }),
    ).toBeInTheDocument()
  })

  it('does not leak raw exception', async () => {
    const error = new Error('secret internal stack')
    mockedExplainMatch.mockRejectedValue(error)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.queryByText(/secret internal stack/i)).not.toBeInTheDocument()
    expect(
      screen.getByText(
        'Không thể kết nối tới máy chủ. Vui lòng kiểm tra kết nối và thử lại.',
      ),
    ).toBeInTheDocument()
  })

  it('retries after failure', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 422, data: { detail: 'Invalid payload' } },
    })
    mockedExplainMatch
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(mockExplanation as never)

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(
        screen.getByText('The candidate matches the role well.'),
      ).toBeInTheDocument()
    })
    expect(mockedExplainMatch).toHaveBeenCalledTimes(2)
  })

  it('closes the modal', async () => {
    mockedExplainMatch.mockResolvedValue(mockExplanation as never)
    const onClose = vi.fn()

    render(
      <ExplainMatchModal
        matchResult={mockMatchResult}
        onClose={onClose}
      />,
    )

    await waitFor(() => {
      expect(
        screen.getByText('The candidate matches the role well.'),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByRole('button', { name: /Đóng/i })[0])

    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
