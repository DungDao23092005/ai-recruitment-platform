import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AIChatPage } from './AIChatPage'
import { sendChatMessage } from '@/api/ai'
import type { ChatResponse } from '@/types/ai'

const mockResponse: ChatResponse = {
  answer: 'Dựa trên dữ kiện, bạn nên học **Python**.',
  confidence: 0.9,
  sources: [
    {
      source_type: 'job',
      entity_id: 'job-1',
      title: 'Job abc12345',
      relevance_score: 0.87,
      skills: ['Python', 'FastAPI'],
    },
  ],
  suggested_followups: ['Lộ trình AI Engineer?'],
}

vi.mock('@/api/ai', () => ({
  sendChatMessage: vi.fn(),
}))

const mockedSendChatMessage = vi.mocked(sendChatMessage)

beforeEach(() => {
  vi.resetAllMocks()
  mockedSendChatMessage.mockResolvedValue(mockResponse)
})

describe('AIChatPage', () => {
  it('renders starter prompts', () => {
    render(<AIChatPage />)

    expect(
      screen.getByRole('button', {
        name: /Tư vấn lộ trình phát triển kỹ năng AI Engineer/i,
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', {
        name: /Những kỹ năng cần thiết cho vị trí Fullstack Developer/i,
      }),
    ).toBeInTheDocument()
  })

  it('renders the page title', () => {
    render(<AIChatPage />)

    expect(
      screen.getByRole('heading', { name: 'Trợ lý AI tuyển dụng' }),
    ).toBeInTheDocument()
  })

  it('sends a typed message', async () => {
    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Tư vấn lộ trình AI' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(mockedSendChatMessage).toHaveBeenCalled()
    })
    expect(mockedSendChatMessage.mock.calls[0][0]).toEqual({
      message: 'Tư vấn lộ trình AI',
      history: [],
    })
  })

  it('sends from starter prompt', async () => {
    render(<AIChatPage />)

    fireEvent.click(
      screen.getByRole('button', {
        name: /Tư vấn lộ trình phát triển kỹ năng AI Engineer/i,
      }),
    )

    await waitFor(() => {
      expect(mockedSendChatMessage).toHaveBeenCalled()
    })
    expect(mockedSendChatMessage.mock.calls[0][0].message).toBe(
      'Tư vấn lộ trình phát triển kỹ năng AI Engineer',
    )
  })

  it('shows loading state while waiting', async () => {
    mockedSendChatMessage.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockResponse), 50)),
    )

    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(screen.getByText('AI đang trả lời...')).toBeInTheDocument()
    })
  })

  it('renders the user message and AI response', async () => {
    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi gì đó' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(screen.getByText('Câu hỏi gì đó')).toBeInTheDocument()
      expect(screen.getByText('Python')).toBeInTheDocument()
    })
  })

  it('keeps history across messages', async () => {
    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi đầu tiên' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(screen.getByText('Câu hỏi đầu tiên')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi thứ hai' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(mockedSendChatMessage).toHaveBeenCalledTimes(2)
    })
    const secondCall = mockedSendChatMessage.mock.calls[1][0]
    expect(secondCall.message).toBe('Câu hỏi thứ hai')
    expect(secondCall.history).toHaveLength(2)
  })

  it('renders citations', async () => {
    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(screen.getByText('Nguồn tham khảo')).toBeInTheDocument()
      expect(screen.getByText('Job abc12345')).toBeInTheDocument()
      expect(screen.getByLabelText('Độ liên quan 87%')).toBeInTheDocument()
    })
  })

  it('renders suggested followups and sends on click', async () => {
    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Lộ trình AI Engineer?' }),
      ).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: 'Lộ trình AI Engineer?' }),
    )

    await waitFor(() => {
      expect(mockedSendChatMessage).toHaveBeenCalledTimes(2)
    })
    expect(mockedSendChatMessage.mock.calls[1][0].message).toBe(
      'Lộ trình AI Engineer?',
    )
  })

  it('shows error with retry', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 502, data: { detail: 'Search failed' } },
    })
    mockedSendChatMessage
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(mockResponse)

    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('Python')).toBeInTheDocument()
    })
    expect(mockedSendChatMessage).toHaveBeenCalledTimes(2)
  })

  it('disables input while loading', async () => {
    mockedSendChatMessage.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockResponse), 50)),
    )

    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Đang gửi\.\.\./i }),
      ).toBeDisabled()
    })
  })
})
