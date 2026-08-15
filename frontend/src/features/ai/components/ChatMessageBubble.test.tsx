import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  ChatMessageBubble,
  formatSourceScore,
  renderMarkdown,
} from './ChatMessageBubble'
import type { ChatMessage, ChatSource } from '@/types/ai'

const userMessage: ChatMessage = {
  role: 'user',
  content: 'Tư vấn lộ trình AI Engineer',
}

const aiMessage: ChatMessage = {
  role: 'assistant',
  content: 'Dựa trên dữ kiện, bạn nên học **Python** và `FastAPI`.',
}

const sources: ChatSource[] = [
  {
    source_type: 'job',
    entity_id: 'job-1',
    title: 'Job abc12345',
    relevance_score: 0.87,
    skills: ['Python', 'FastAPI'],
  },
]

describe('ChatMessageBubble', () => {
  it('renders a user message', () => {
    render(<ChatMessageBubble message={userMessage} />)

    expect(screen.getByText('Tư vấn lộ trình AI Engineer')).toBeInTheDocument()
  })

  it('renders an AI message with markdown', () => {
    render(<ChatMessageBubble message={aiMessage} />)

    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.getByText('FastAPI')).toBeInTheDocument()
  })

  it('renders citations with relevance score', () => {
    render(<ChatMessageBubble message={aiMessage} sources={sources} />)

    expect(screen.getByText('Nguồn tham khảo')).toBeInTheDocument()
    expect(screen.getByText('Job abc12345')).toBeInTheDocument()
    expect(screen.getByText(/Python, FastAPI/)).toBeInTheDocument()
    expect(screen.getByLabelText('Độ liên quan 87%')).toBeInTheDocument()
  })

  it('does not render citations when none provided', () => {
    render(<ChatMessageBubble message={aiMessage} />)

    expect(screen.queryByText('Nguồn tham khảo')).not.toBeInTheDocument()
  })

  it('renders suggested followups', () => {
    const onFollowupClick = vi.fn()

    render(
      <ChatMessageBubble
        message={aiMessage}
        suggestedFollowups={['Lộ trình AI Engineer?']}
        onFollowupClick={onFollowupClick}
      />,
    )

    const button = screen.getByRole('button', { name: 'Lộ trình AI Engineer?' })
    expect(button).toBeInTheDocument()

    fireEvent.click(button)
    expect(onFollowupClick).toHaveBeenCalledWith('Lộ trình AI Engineer?')
  })

  it('formats score as percentage', () => {
    expect(formatSourceScore(0.87)).toBe('87%')
    expect(formatSourceScore(0.5)).toBe('50%')
    expect(formatSourceScore(Number.NaN)).toBe('0%')
  })

  it('renders markdown bold and code', () => {
    const { container } = render(
      <div>{renderMarkdown('Học **Python** và `FastAPI`.')}</div>,
    )

    expect(container.querySelector('strong')).toHaveTextContent('Python')
    expect(container.querySelector('code')).toHaveTextContent('FastAPI')
  })

  it('renders markdown lists', () => {
    const { container } = render(
      <div>{renderMarkdown('- Một\n- Hai\n- Ba')}</div>,
    )

    expect(container.querySelectorAll('li')).toHaveLength(3)
  })

  it('renders markdown headings', () => {
    const { container } = render(
      <div>{renderMarkdown('# Tiêu đề')}</div>,
    )

    expect(container.querySelector('h2')).toHaveTextContent('Tiêu đề')
  })
})
