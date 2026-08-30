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
      expect(screen.getByRole('button', { name: /Đang gửi\.\.\./i })).toBeDisabled()
    })
  })

  it('preserves conversation when clicking suggested followup', async () => {
    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi ban đầu' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(screen.getByText('Câu hỏi ban đầu')).toBeInTheDocument()
      expect(screen.getByText('Python')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Lộ trình AI Engineer?' }),
      ).toBeInTheDocument()
    })

    // Click the suggestion button
    const suggestionButton = screen.getByRole('button', { name: 'Lộ trình AI Engineer?' })
    fireEvent.click(suggestionButton)

    await waitFor(() => {
      expect(screen.getByText('Câu hỏi ban đầu')).toBeInTheDocument()
      // Two "Python" occurrences: one from each AI response
      expect(screen.getAllByText('Python')).toHaveLength(2)
      // The suggestion button should still exist (from the latest AI response)
      expect(screen.getAllByRole('button', { name: 'Lộ trình AI Engineer?' }).length).toBeGreaterThanOrEqual(1)
      // Check for the AI response text using a partial match (there are two now, use getAllByText)
      expect(screen.getAllByText(/Dựa trên dữ kiện, bạn nên học/).length).toBeGreaterThanOrEqual(1)
    })
  })

  it('prevents multiple concurrent requests on rapid suggestion clicks', async () => {
    let firstResolve: (value: typeof mockResponse) => void
    const firstPromise = new Promise<typeof mockResponse>((resolve) => {
      firstResolve = resolve
    })

    let secondResolve: (value: typeof mockResponse) => void
    const secondPromise = new Promise<typeof mockResponse>((resolve) => {
      secondResolve = resolve
    })

    mockedSendChatMessage
      .mockReturnValueOnce(firstPromise)
      .mockReturnValueOnce(secondPromise)

    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    // Resolve first request so suggestion button appears
    firstResolve!(mockResponse)

    // Wait for first response and suggestion button to appear
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Lộ trình AI Engineer?' }),
      ).toBeInTheDocument()
    })

    const suggestionButton = screen.getByRole('button', {
      name: 'Lộ trình AI Engineer?',
    })

    // Rapidly click the suggestion 3 times
    fireEvent.click(suggestionButton)
    fireEvent.click(suggestionButton)
    fireEvent.click(suggestionButton)

    // Should only call sendChatMessage once more (the lock should prevent duplicates)
    await waitFor(() => {
      expect(mockedSendChatMessage).toHaveBeenCalledTimes(2) // 1 initial + 1 suggestion
    })

    secondResolve!(mockResponse)

    await waitFor(() => {
      expect(screen.getByText(/Dựa trên dữ kiện, bạn nên học/)).toBeInTheDocument()
    })
  })

  it('scrolls local chat container on new messages', async () => {
    const scrollToSpy = vi.fn()

    // Mock scrollTo on HTMLElement prototype
    const originalScrollTo = HTMLElement.prototype.scrollTo
    HTMLElement.prototype.scrollTo = scrollToSpy

    mockedSendChatMessage.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockResponse), 10)),
    )

    render(<AIChatPage />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Câu hỏi test scroll' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(screen.getByText('Câu hỏi test scroll')).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByText('Python')).toBeInTheDocument()
    })

    expect(scrollToSpy).toHaveBeenCalled()

    HTMLElement.prototype.scrollTo = originalScrollTo
  })
})