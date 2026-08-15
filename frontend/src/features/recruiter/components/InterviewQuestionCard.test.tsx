import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  InterviewQuestionCard,
  CATEGORY_LABELS,
  DIFFICULTY_LABELS,
} from './InterviewQuestionCard'
import type { InterviewQuestion } from '@/types/ai'

const question: InterviewQuestion = {
  question: 'Explain how you handle React state.',
  category: 'technical',
  difficulty: 'medium',
  target_skill_or_topic: 'React state management',
  evaluation_criteria:
    'Demonstrates understanding of state management trade-offs.',
  sample_answer_points: ['Mentions hooks', 'Explains re-render behavior'],
}

describe('InterviewQuestionCard', () => {
  it('renders the question with index', () => {
    render(<InterviewQuestionCard index={0} question={question} />)

    expect(
      screen.getByText('Explain how you handle React state.'),
    ).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('renders category label', () => {
    render(<InterviewQuestionCard index={0} question={question} />)

    expect(screen.getByText(CATEGORY_LABELS.technical)).toBeInTheDocument()
  })

  it('renders difficulty label', () => {
    render(<InterviewQuestionCard index={0} question={question} />)

    expect(screen.getByText(DIFFICULTY_LABELS.medium)).toBeInTheDocument()
  })

  it('renders target skill or topic', () => {
    render(<InterviewQuestionCard index={0} question={question} />)

    expect(
      screen.getByText('React state management'),
    ).toBeInTheDocument()
  })

  it('renders evaluation criteria', () => {
    render(<InterviewQuestionCard index={0} question={question} />)

    expect(
      screen.getByText('Demonstrates understanding of state management trade-offs.'),
    ).toBeInTheDocument()
  })

  it('renders sample answer points', () => {
    render(<InterviewQuestionCard index={0} question={question} />)

    expect(screen.getByText('Mentions hooks')).toBeInTheDocument()
    expect(screen.getByText('Explains re-render behavior')).toBeInTheDocument()
  })

  it('renders category label map correctly', () => {
    expect(CATEGORY_LABELS.behavioral).toBe('Hành vi')
    expect(CATEGORY_LABELS.experience).toBe('Kinh nghiệm')
    expect(CATEGORY_LABELS.skill_gap).toBe('Khoảng cách kỹ năng')
    expect(DIFFICULTY_LABELS.easy).toBe('Dễ')
    expect(DIFFICULTY_LABELS.hard).toBe('Khó')
  })
})
