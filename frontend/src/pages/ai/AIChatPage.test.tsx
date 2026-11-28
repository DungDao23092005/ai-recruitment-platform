import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'

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

  // UI-04 Regression Tests: Retry logic with isRetry flag
  describe('Retry logic (UI-04)', () => {
    it('A. Send message successfully → exactly one user message', async () => {
      const user = userEvent.setup()
      render(<AIChatPage />)

      await user.type(screen.getByLabelText('Tin nhắn chat'), 'Hello AI')
      await user.click(screen.getByRole('button', { name: /Gửi/i }))

      await waitFor(() => {
        expect(screen.getByText('Hello AI')).toBeInTheDocument()
      })

      // Exactly one user message
      const userMessages = screen.getAllByText('Hello AI')
      expect(userMessages).toHaveLength(1)
    })

    it('B. Send message → API failure → user message remains exactly once', async () => {
      const user = userEvent.setup()
      const error = new Error('Bad Request')
      Object.assign(error, {
        response: { status: 502, data: { detail: 'Search failed' } },
      })
      mockedSendChatMessage.mockRejectedValueOnce(error)

      render(<AIChatPage />)

      await user.type(screen.getByLabelText('Tin nhắn chat'), 'Test failure')
      await user.click(screen.getByRole('button', { name: /Gửi/i }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
      })

      // User message should appear exactly once
      const userMessages = screen.getAllByText('Test failure')
      expect(userMessages).toHaveLength(1)
    })

    it('C. Click Retry → retry request occurs', async () => {
      const user = userEvent.setup()
      const error = new Error('Bad Request')
      Object.assign(error, {
        response: { status: 502, data: { detail: 'Search failed' } },
      })
      mockedSendChatMessage
        .mockRejectedValueOnce(error)
        .mockResolvedValueOnce(mockResponse)

      render(<AIChatPage />)

      await user.type(screen.getByLabelText('Tin nhắn chat'), 'Retry test')
      await user.click(screen.getByRole('button', { name: /Gửi/i }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
      })

      // Click Retry
      await user.click(screen.getByRole('button', { name: /Thử lại/i }))

      // Retry request should occur
      await waitFor(() => {
        expect(mockedSendChatMessage).toHaveBeenCalledTimes(2)
      })
    })

    it('D. After Retry → number of user messages remains unchanged', async () => {
      const user = userEvent.setup()
      const error = new Error('Bad Request')
      Object.assign(error, {
        response: { status: 502, data: { detail: 'Search failed' } },
      })
      mockedSendChatMessage
        .mockRejectedValueOnce(error)
        .mockResolvedValueOnce(mockResponse)

      render(<AIChatPage />)

      await user.type(screen.getByLabelText('Tin nhắn chat'), 'Retry message')
      await user.click(screen.getByRole('button', { name: /Gửi/i }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
      })

      // Count user messages before retry
      const userMessagesBeforeRetry = screen.getAllByText('Retry message')
      expect(userMessagesBeforeRetry).toHaveLength(1)

      // Click Retry
      await user.click(screen.getByRole('button', { name: /Thử lại/i }))

      await waitFor(() => {
        expect(screen.getByText('Python')).toBeInTheDocument()
      })

      // User messages should remain exactly 1 (no duplicate)
      const userMessagesAfterRetry = screen.getAllByText('Retry message')
      expect(userMessagesAfterRetry).toHaveLength(1)
    })

    it('E. Successful retry → exactly one assistant response', async () => {
      const user = userEvent.setup()
      const error = new Error('Bad Request')
      Object.assign(error, {
        response: { status: 502, data: { detail: 'Search failed' } },
      })
      mockedSendChatMessage
        .mockRejectedValueOnce(error)
        .mockResolvedValueOnce(mockResponse)

      render(<AIChatPage />)

      await user.type(screen.getByLabelText('Tin nhắn chat'), 'Successful retry')
      await user.click(screen.getByRole('button', { name: /Gửi/i }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
      })

      // Click Retry
      await user.click(screen.getByRole('button', { name: /Thử lại/i }))

      await waitFor(() => {
        expect(screen.getByText('Python')).toBeInTheDocument()
      })

      // Exactly one assistant response (the successful retry)
      const assistantResponses = screen.getAllByText(/Dựa trên dữ kiện, bạn nên học/)
      expect(assistantResponses).toHaveLength(1)
    })

    it('F. Multiple retries → no duplicate user messages', async () => {
      const user = userEvent.setup()
      const error = new Error('Bad Request')
      Object.assign(error, {
        response: { status: 502, data: { detail: 'Search failed' } },
      })
      // Fail twice, then succeed on third attempt
      mockedSendChatMessage
        .mockRejectedValueOnce(error)
        .mockRejectedValueOnce(error)
        .mockResolvedValueOnce(mockResponse)

      render(<AIChatPage />)

      await user.type(screen.getByLabelText('Tin nhắn chat'), 'Multiple retries')
      await user.click(screen.getByRole('button', { name: /Gửi/i }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
      })

      // First retry
      await user.click(screen.getByRole('button', { name: /Thử lại/i }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
      })

      // Second retry
      await user.click(screen.getByRole('button', { name: /Thử lại/i }))

      await waitFor(() => {
        expect(screen.getByText('Python')).toBeInTheDocument()
      })

      // User messages should remain exactly 1 (no duplicates from multiple retries)
      const userMessages = screen.getAllByText('Multiple retries')
      expect(userMessages).toHaveLength(1)

      // Exactly one assistant response
      const assistantResponses = screen.getAllByText(/Dựa trên dữ kiện, bạn nên học/)
      expect(assistantResponses).toHaveLength(1)
    })
  })

  it('preserves recommended_job_ids across multi-turn history', async () => {
    const user = userEvent.setup()
    mockedSendChatMessage
      .mockResolvedValueOnce({
        answer: 'Các vị trí phù hợp gồm Backend Python.',
        confidence: 0.92,
        sources: [
          {
            source_type: 'job',
            entity_id: '11111111-1111-1111-1111-111111111111',
            title: 'Backend Python',
            relevance_score: 0.92,
            skills: ['Python', 'FastAPI'],
          },
        ],
        suggested_followups: ['Tại sao tôi phù hợp?'],
        recommended_job_ids: ['11111111-1111-1111-1111-111111111111'],
      })
      .mockResolvedValueOnce({
        answer: 'Bạn có Python phù hợp với Backend Python.',
        confidence: 0.9,
        sources: [],
        suggested_followups: [],
        recommended_job_ids: ['11111111-1111-1111-1111-111111111111'],
      })

    render(<AIChatPage />)

    await user.type(
      screen.getByLabelText('Tin nhắn chat'),
      'cv của tôi hiện tại phù hợp với những công việc gì',
    )
    await user.click(screen.getByRole('button', { name: /Gửi/i }))

    await waitFor(() => {
      expect(
        screen.getByText(/Các vị trí phù hợp gồm Backend Python/),
      ).toBeInTheDocument()
    })

    await user.click(
      screen.getByRole('button', { name: 'Tại sao tôi phù hợp?' }),
    )

    await waitFor(() => {
      expect(mockedSendChatMessage).toHaveBeenCalledTimes(2)
    })

    const secondCallHistory = mockedSendChatMessage.mock.calls[1][0].history
    expect(secondCallHistory).toEqual([
      {
        role: 'user',
        content: 'cv của tôi hiện tại phù hợp với những công việc gì',
      },
      {
        role: 'assistant',
        content: 'Các vị trí phù hợp gồm Backend Python.',
        recommended_job_ids: ['11111111-1111-1111-1111-111111111111'],
      },
    ])
    expect(mockedSendChatMessage.mock.calls[1][0].recommended_job_ids).toEqual([
      '11111111-1111-1111-1111-111111111111',
    ])
  })

  it('accumulates recommended_job_ids across turns and preserves them after history exceeds 10 messages', async () => {
    const user = userEvent.setup()
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Gợi ý ban đầu gồm Job 1 và Job 2.',
      confidence: 0.9,
      sources: [],
      suggested_followups: [],
      recommended_job_ids: ['job-1', 'job-2'],
    })
    for (let i = 0; i < 5; i += 1) {
      mockedSendChatMessage.mockResolvedValueOnce({
        answer: `Followup reply ${i + 1}`,
        confidence: 0.85,
        sources: [],
        suggested_followups: [],
        recommended_job_ids: i === 0 ? ['job-2', 'job-3'] : [],
      })
    }
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Chi tiết đầy đủ.',
      confidence: 0.9,
      sources: [],
      suggested_followups: [],
    })

    render(<AIChatPage />)
    const input = screen.getByLabelText('Tin nhắn chat')

    // Turn 1 sets ['job-1', 'job-2']
    await user.type(input, 'Turn 1')
    await user.click(screen.getByRole('button', { name: /Gửi/i }))
    await waitFor(() => expect(mockedSendChatMessage).toHaveBeenCalledTimes(1))

    // Turns 2..6 push total visible messages past 10; Turn 2 adds 'job-3', Turns 3..6 return []
    for (let i = 0; i < 5; i += 1) {
      await user.type(input, `Follow ${i + 1}`)
      await user.click(screen.getByRole('button', { name: /Gửi/i }))
      await waitFor(() => expect(mockedSendChatMessage).toHaveBeenCalledTimes(i + 2))
    }

    // Turn 7 (now history has been sliced to last 10, evicting Turn 1 assistant message)
    await user.type(input, 'Final question')
    await user.click(screen.getByRole('button', { name: /Gửi/i }))
    await waitFor(() => expect(mockedSendChatMessage).toHaveBeenCalledTimes(7))

    const lastPayload = mockedSendChatMessage.mock.calls[6][0]
    expect(lastPayload.history).toHaveLength(10)
    expect(lastPayload.recommended_job_ids).toEqual(['job-1', 'job-2', 'job-3'])
  })

  it('preserves all 7 Turn-0 recommended_job_ids across 8 sequential exchanges without overwriting or leaking after history window eviction', async () => {
    const user = userEvent.setup({ delay: null })
    const sevenIds = ['job-1', 'job-2', 'job-3', 'job-4', 'job-5', 'job-6', 'job-7']

    // Exchange 1 (Turn 0): returns all 7 recommended IDs
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Gợi ý 7 vị trí phù hợp nhất cho bạn.',
      confidence: 0.92,
      sources: [],
      suggested_followups: [],
      recommended_job_ids: sevenIds,
    })
    // Exchange 2: single-job response must NOT overwrite 7-ID set
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Machine Learning Engineer liên quan nhiều nhất đến AI.',
      confidence: 0.88,
      sources: [],
      suggested_followups: [],
      recommended_job_ids: ['job-2'],
    })
    // Exchange 3: another single-job response
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Để ứng tuyển Machine Learning Engineer cần bổ sung PyTorch.',
      confidence: 0.87,
      sources: [],
      suggested_followups: [],
      recommended_job_ids: ['job-2'],
    })
    // Exchange 4: best match justification (job-1)
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Bạn phù hợp với Test Job nhờ kỹ năng nền tảng.',
      confidence: 0.89,
      sources: [],
      suggested_followups: [],
      recommended_job_ids: ['job-1'],
    })
    // Exchange 5: intermediate CV summary returns empty recommended_job_ids -> must NOT clear 7 IDs
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Tóm tắt hồ sơ: Senior Python Engineer với 4 năm kinh nghiệm.',
      confidence: 0.9,
      sources: [],
      suggested_followups: [],
      recommended_job_ids: [],
    })
    // Exchange 6: follow-up after CV summary
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Tổng hợp kỹ năng còn thiếu cho cả 7 vị trí.',
      confidence: 0.86,
      sources: [],
      suggested_followups: [],
      recommended_job_ids: sevenIds,
    })
    // Exchange 7: detailed scores response omits recommended_job_ids -> still preserved
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Chi tiết mức độ phù hợp của 7 vị trí.',
      confidence: 0.88,
      sources: [],
      suggested_followups: [],
    })
    // Exchange 8: specific role Backend Developer (Python) after Turn-0 left sliding window
    mockedSendChatMessage.mockResolvedValueOnce({
      answer: 'Backend Developer (Python) cần bổ sung Kubernetes.',
      confidence: 0.87,
      sources: [],
      suggested_followups: [],
      recommended_job_ids: ['job-3'],
    })

    render(<AIChatPage />)
    const input = screen.getByLabelText('Tin nhắn chat')
    const prompts = [
      'cv của tôi hiện tại phù hợp với những công việc gì có trong hệ thống',
      'Vị trí nào liên quan nhiều nhất đến AI?',
      'Tôi cần bổ sung kỹ năng gì để ứng tuyển vị trí Machine Learning Engineer?',
      'Tại sao tôi phù hợp với vị trí phù hợp nhất?',
      'Hãy tóm tắt hồ sơ của tôi',
      'Tôi còn thiếu kỹ năng gì cho các vị trí trên?',
      'Chi tiết mức độ phù hợp cho từng vị trí là bao nhiêu?',
      'Tôi cần bổ sung kỹ năng gì cho vị trí Backend Developer (Python)?',
    ]

    for (let i = 0; i < prompts.length; i += 1) {
      await user.type(input, prompts[i])
      await user.click(screen.getByRole('button', { name: /Gửi/i }))
      await waitFor(() => expect(mockedSendChatMessage).toHaveBeenCalledTimes(i + 1))

      const payload = mockedSendChatMessage.mock.calls[i][0]
      expect(payload.history.length).toBeLessThanOrEqual(10)
      if (i === 0) {
        expect(payload.recommended_job_ids).toBeUndefined()
      } else {
        expect(payload.recommended_job_ids).toEqual(sevenIds)
      }
    }

    // Exchanges 6, 7, 8 (indices 5, 6, 7) are past the 10-message sliding window so Turn-0 messages are evicted
    expect(mockedSendChatMessage.mock.calls[5][0].history).toHaveLength(10)
    expect(mockedSendChatMessage.mock.calls[6][0].history).toHaveLength(10)
    expect(mockedSendChatMessage.mock.calls[7][0].history).toHaveLength(10)
    expect(
      mockedSendChatMessage.mock.calls[7][0].history.some((m) =>
        m.content.includes('cv của tôi hiện tại phù hợp với những công việc gì'),
      ),
    ).toBe(false)
    expect(mockedSendChatMessage.mock.calls[7][0].recommended_job_ids).toEqual(sevenIds)
  })

  it('isolates recommended_job_ids when AIChatPage unmounts and remounts', async () => {
    const user = userEvent.setup()
    mockedSendChatMessage
      .mockResolvedValueOnce({
        answer: 'Session A jobs',
        confidence: 0.9,
        sources: [],
        suggested_followups: [],
        recommended_job_ids: ['job-session-a-1', 'job-session-a-2'],
      })
      .mockResolvedValueOnce({
        answer: 'Session B reply',
        confidence: 0.85,
        sources: [],
        suggested_followups: [],
        recommended_job_ids: [],
      })

    const { unmount } = render(<AIChatPage />)
    await user.type(screen.getByLabelText('Tin nhắn chat'), 'Gợi ý cho tôi')
    await user.click(screen.getByRole('button', { name: /Gửi/i }))
    await waitFor(() => expect(mockedSendChatMessage).toHaveBeenCalledTimes(1))

    unmount()

    render(<AIChatPage />)
    await user.type(screen.getByLabelText('Tin nhắn chat'), 'Hỏi mới ở phiên mới')
    await user.click(screen.getByRole('button', { name: /Gửi/i }))
    await waitFor(() => expect(mockedSendChatMessage).toHaveBeenCalledTimes(2))

    expect(mockedSendChatMessage.mock.calls[1][0].recommended_job_ids).toBeUndefined()
    expect(mockedSendChatMessage.mock.calls[1][0].history).toEqual([])
  })
})