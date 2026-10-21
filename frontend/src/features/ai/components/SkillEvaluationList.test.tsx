import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  SkillEvaluationList,
  groupSkillEvaluations,
} from './SkillEvaluationList'
import type { EvidenceExcerpt, SkillEvaluation } from '@/types/ai'

function makeSkill(
  overrides: Partial<SkillEvaluation> = {},
): SkillEvaluation {
  return {
    skill_name: 'Python',
    requirement_type: 'required',
    status: 'matched_evidenced',
    explanation: "Python is listed in the candidate's skills.",
    evidence: [],
    ...overrides,
  }
}

const sampleEvidence: EvidenceExcerpt = {
  section: 'skills',
  field_name: null,
  item_index: null,
  item_title: null,
  quote: 'Python < FastAPI >',
}

describe('groupSkillEvaluations', () => {
  it('splits required and preferred skills', () => {
    const required = makeSkill({ skill_name: 'Python' })
    const preferred = makeSkill({
      skill_name: 'Docker',
      requirement_type: 'preferred',
    })

    const grouped = groupSkillEvaluations([required, preferred])

    expect(grouped.required).toEqual([required])
    expect(grouped.preferred).toEqual([preferred])
  })
})

describe('SkillEvaluationList', () => {
  it('groups skills under required and preferred regions', () => {
    render(
      <SkillEvaluationList
        evaluations={[
          makeSkill({ skill_name: 'Python', requirement_type: 'required' }),
          makeSkill({
            skill_name: 'Docker',
            requirement_type: 'preferred',
            status: 'partially_matched',
          }),
        ]}
      />,
    )

    const requiredRegion = screen.getByRole('region', {
      name: 'Kỹ năng bắt buộc',
    })
    const preferredRegion = screen.getByRole('region', {
      name: 'Kỹ năng ưu tiên',
    })

    expect(within(requiredRegion).getByText('Python')).toBeInTheDocument()
    expect(within(requiredRegion).queryByText('Docker')).not.toBeInTheDocument()
    expect(within(preferredRegion).getByText('Docker')).toBeInTheDocument()
    expect(within(preferredRegion).queryByText('Python')).not.toBeInTheDocument()
  })

  it('renders every status variant with its Vietnamese label', () => {
    render(
      <SkillEvaluationList
        evaluations={[
          makeSkill({ skill_name: 'A', status: 'matched_evidenced' }),
          makeSkill({ skill_name: 'B', status: 'partially_matched' }),
          makeSkill({ skill_name: 'C', status: 'not_evidenced_in_cv' }),
          makeSkill({ skill_name: 'D', status: 'insufficient_data' }),
        ]}
      />,
    )

    expect(screen.getByText('Đã đối soát trong CV')).toBeInTheDocument()
    expect(screen.getByText('Khớp một phần')).toBeInTheDocument()
    expect(screen.getByText('Chưa thấy dẫn chứng trong CV')).toBeInTheDocument()
    expect(screen.getByText('Chưa đủ dữ liệu')).toBeInTheDocument()
  })

  it('uses neutral wording for skills without CV evidence', () => {
    render(
      <SkillEvaluationList
        evaluations={[makeSkill({ status: 'not_evidenced_in_cv' })]}
      />,
    )

    expect(
      screen.getByText(
        'Không tìm thấy thông tin trong CV được cung cấp; điều này không khẳng định ứng viên thiếu kỹ năng này.',
      ),
    ).toBeInTheDocument()
  })

  it('renders the explanation and supporting evidence', () => {
    render(
      <SkillEvaluationList
        evaluations={[
          makeSkill({
            explanation: 'Có dẫn chứng kỹ năng Python.',
            evidence: [sampleEvidence],
          }),
        ]}
      />,
    )

    expect(screen.getByText('Có dẫn chứng kỹ năng Python.')).toBeInTheDocument()
    expect(screen.getByText('Python < FastAPI >')).toBeInTheDocument()
  })

  it('does not render an evidence block when none is provided', () => {
    const { container } = render(
      <SkillEvaluationList evaluations={[makeSkill({ evidence: [] })]} />,
    )
    expect(container.querySelector('blockquote')).toBeNull()
  })

  it('shows an empty note for a group with no skills', () => {
    render(
      <SkillEvaluationList
        evaluations={[makeSkill({ requirement_type: 'required' })]}
      />,
    )
    expect(screen.getByText('Không có kỹ năng ưu tiên.')).toBeInTheDocument()
  })

  it('shows an empty state when there are no evaluations', () => {
    render(<SkillEvaluationList evaluations={[]} />)
    expect(
      screen.getByText('Chưa có đánh giá kỹ năng để hiển thị.'),
    ).toBeInTheDocument()
  })
})
