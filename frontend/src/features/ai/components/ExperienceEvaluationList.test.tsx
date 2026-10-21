import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  ExperienceEvaluationList,
  getExperienceRelevanceMeta,
} from './ExperienceEvaluationList'
import type { EvidenceExcerpt, ExperienceEvaluation } from '@/types/ai'

function makeExperience(
  overrides: Partial<ExperienceEvaluation> = {},
): ExperienceEvaluation {
  return {
    role_title: 'Senior Engineer',
    company: 'Acme Corp',
    duration: '2020 — Present',
    relevance: 'relevant_skills',
    explanation: 'Role used required skills: Python.',
    evidence: [],
    ...overrides,
  }
}

const sampleEvidence: EvidenceExcerpt = {
  section: 'experiences',
  field_name: 'skills_used',
  item_index: 0,
  item_title: 'Senior Engineer',
  quote: 'Led platform team building microservices',
}

describe('getExperienceRelevanceMeta', () => {
  it('maps known deterministic relevance labels', () => {
    expect(getExperienceRelevanceMeta('relevant_skills').variant).toBe('success')
    expect(getExperienceRelevanceMeta('no_required_skill_overlap').variant).toBe(
      'neutral',
    )
    expect(getExperienceRelevanceMeta('no_overlap_with_requirements').variant).toBe(
      'neutral',
    )
    expect(getExperienceRelevanceMeta('no_requirement_to_compare').variant).toBe(
      'info',
    )
  })

  it('falls back to a neutral label for unknown relevance values', () => {
    const meta = getExperienceRelevanceMeta('custom_label')
    expect(meta.label).toBe('custom_label')
    expect(meta.variant).toBe('neutral')
  })
})

describe('ExperienceEvaluationList', () => {
  it('renders role, company, duration, explanation and relevance', () => {
    render(<ExperienceEvaluationList evaluations={[makeExperience()]} />)

    expect(screen.getByText('Senior Engineer · Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('2020 — Present')).toBeInTheDocument()
    expect(
      screen.getByText('Role used required skills: Python.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Sử dụng kỹ năng yêu cầu'),
    ).toBeInTheDocument()
  })

  it('renders supporting evidence as literal text', () => {
    render(
      <ExperienceEvaluationList
        evaluations={[makeExperience({ evidence: [sampleEvidence] })]}
      />,
    )
    expect(
      screen.getByText('Led platform team building microservices'),
    ).toBeInTheDocument()
  })

  it('renders null role, company and duration without inventing data', () => {
    render(
      <ExperienceEvaluationList
        evaluations={[
          makeExperience({
            role_title: null,
            company: null,
            duration: null,
          }),
        ]}
      />,
    )

    expect(screen.getByText('Chưa có thông tin chức danh')).toBeInTheDocument()
    expect(screen.queryByText('2020 — Present')).not.toBeInTheDocument()
  })

  it('renders a role when only the company is missing', () => {
    render(
      <ExperienceEvaluationList
        evaluations={[makeExperience({ company: null })]}
      />,
    )
    expect(screen.getByText('Senior Engineer')).toBeInTheDocument()
    expect(screen.queryByText(/·/)).not.toBeInTheDocument()
  })

  it('renders each relevance label', () => {
    render(
      <ExperienceEvaluationList
        evaluations={[
          makeExperience({ relevance: 'relevant_skills' }),
          makeExperience({ relevance: 'no_required_skill_overlap' }),
          makeExperience({ relevance: 'no_requirement_to_compare' }),
        ]}
      />,
    )

    expect(screen.getByText('Sử dụng kỹ năng yêu cầu')).toBeInTheDocument()
    expect(screen.getByText('Chưa thấy kỹ năng yêu cầu')).toBeInTheDocument()
    expect(
      screen.getByText('Không có yêu cầu để đối chiếu'),
    ).toBeInTheDocument()
  })

  it('handles a long list of experiences', () => {
    const evaluations = Array.from({ length: 12 }, (_, index) =>
      makeExperience({ role_title: `Role ${index}` }),
    )
    render(<ExperienceEvaluationList evaluations={evaluations} />)
    expect(screen.getByText('Role 0 · Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Role 11 · Acme Corp')).toBeInTheDocument()
  })

  it('shows an empty state when there are no experiences', () => {
    render(<ExperienceEvaluationList evaluations={[]} />)
    expect(
      screen.getByText('Chưa có kinh nghiệm để đối chiếu.'),
    ).toBeInTheDocument()
  })
})
