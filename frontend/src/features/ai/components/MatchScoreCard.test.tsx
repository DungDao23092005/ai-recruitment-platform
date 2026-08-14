import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  MatchScoreCard,
  getScoreColor,
  formatPercent,
} from './MatchScoreCard'
import type { MatchResult } from '@/types/ai'

const highMatch: MatchResult = {
  overall_score: 85,
  cosine_similarity: 0.9,
  skill_coverage_score: 0.8,
  experience_match_score: 0.7,
  matching_skills: ['React', 'TypeScript'],
  skill_gap: ['GraphQL'],
  match_reasons: ['Strong skill overlap', 'Relevant experience'],
}

const mediumMatch: MatchResult = {
  ...highMatch,
  overall_score: 60,
  cosine_similarity: 0.5,
}

const lowMatch: MatchResult = {
  ...highMatch,
  overall_score: 40,
  cosine_similarity: 0.3,
}

describe('getScoreColor', () => {
  it('returns emerald for score >= 75', () => {
    const color = getScoreColor(85)
    expect(color.text).toContain('emerald')
  })

  it('returns amber for 50 <= score < 75', () => {
    const color = getScoreColor(60)
    expect(color.text).toContain('amber')
  })

  it('returns rose for score < 50', () => {
    const color = getScoreColor(40)
    expect(color.text).toContain('rose')
  })
})

describe('formatPercent', () => {
  it('formats a 0-1 value as a percent', () => {
    expect(formatPercent(0.9)).toBe('90%')
  })

  it('returns 0% for NaN', () => {
    expect(formatPercent(Number.NaN)).toBe('0%')
  })
})

describe('MatchScoreCard', () => {
  it('renders the overall score', () => {
    render(<MatchScoreCard matchResult={highMatch} />)
    expect(
      screen.getByLabelText('Overall score 85 percent'),
    ).toBeInTheDocument()
    expect(screen.getAllByText('85%').length).toBeGreaterThan(0)
  })

  it('renders the score breakdown', () => {
    render(<MatchScoreCard matchResult={highMatch} />)
    expect(screen.getByText('Cosine Similarity')).toBeInTheDocument()
    expect(screen.getByText('Skill Coverage')).toBeInTheDocument()
    expect(screen.getByText('Experience Match')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByText('70%')).toBeInTheDocument()
  })

  it('renders matching skills', () => {
    render(<MatchScoreCard matchResult={highMatch} />)
    expect(screen.getByText('React')).toBeInTheDocument()
    expect(screen.getByText('TypeScript')).toBeInTheDocument()
  })

  it('renders skill gaps', () => {
    render(<MatchScoreCard matchResult={highMatch} />)
    expect(screen.getByText('GraphQL')).toBeInTheDocument()
  })

  it('renders match reasons', () => {
    render(<MatchScoreCard matchResult={highMatch} />)
    expect(screen.getByText('Strong skill overlap')).toBeInTheDocument()
    expect(screen.getByText('Relevant experience')).toBeInTheDocument()
  })

  it('shows a placeholder when there are no matching skills', () => {
    render(
      <MatchScoreCard matchResult={{ ...highMatch, matching_skills: [] }} />,
    )
    expect(
      screen.getByText('No matching skills found.'),
    ).toBeInTheDocument()
  })

  it('shows a placeholder when there are no skill gaps', () => {
    render(<MatchScoreCard matchResult={{ ...highMatch, skill_gap: [] }} />)
    expect(
      screen.getByText('No skill gaps detected.'),
    ).toBeInTheDocument()
  })

  it('uses medium color class for a medium score', () => {
    const { container } = render(
      <MatchScoreCard matchResult={mediumMatch} />,
    )
    expect(container.querySelector('.text-amber-600')).not.toBeNull()
  })

  it('uses low color class for a low score', () => {
    const { container } = render(<MatchScoreCard matchResult={lowMatch} />)
    expect(container.querySelector('.text-rose-600')).not.toBeNull()
  })
})