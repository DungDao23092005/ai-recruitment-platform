import { useEffect, useRef, useState } from 'react'
import { Bot, RefreshCw, Sparkles } from 'lucide-react'
import { sendChatMessage } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { ChatMessageBubble } from '@/features/ai/components/ChatMessageBubble'
import { ChatInput } from '@/features/ai/components/ChatInput'
import type { ChatMessage, ChatResponse } from '@/types/ai'

const STARTER_PROMPTS = [
  'Tư vấn lộ trình phát triển kỹ năng AI Engineer',
  'Những kỹ năng cần thiết cho vị trí Fullstack Developer?',
  'Cách tối ưu hóa CV để tăng điểm đối sánh tuyển dụng?',
]

interface DisplayMessage {
  message: ChatMessage
  sources: ChatResponse['sources']
  suggestedFollowups: string[]
}

interface PageState {
  messages: DisplayMessage[]
  isLoading: boolean
  error: string | null
  pendingText: string | null
}

export function AIChatPage() {
  const [state, setState] = useState<PageState>({
    messages: [],
    isLoading: false,
    error: null,
    pendingText: null,
  })
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const scrollToBottom = () => {
    if (typeof bottomRef.current?.scrollIntoView === 'function') {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [state.messages, state.isLoading])

  const send = async (text: string) => {
    if (!text.trim() || state.isLoading) {
      return
    }

    const userMessage: ChatMessage = { role: 'user', content: text.trim() }
    const history: ChatMessage[] = state.messages
      .slice(-10)
      .map((item) => item.message)

    setState((prev) => ({
      ...prev,
      messages: [
        ...prev.messages,
        { message: userMessage, sources: [], suggestedFollowups: [] },
      ],
      isLoading: true,
      error: null,
      pendingText: text.trim(),
    }))

    try {
      const response = await sendChatMessage({
        message: text.trim(),
        history,
      })
      setState((prev) => {
        const assistantMessage: DisplayMessage = {
          message: { role: 'assistant', content: response.reply },
          sources: response.sources,
          suggestedFollowups: response.suggested_followups,
        }
        return {
          ...prev,
          messages: [...prev.messages, assistantMessage],
          isLoading: false,
          error: null,
          pendingText: null,
        }
      })
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: getFriendlyErrorMessage(err),
        pendingText: text.trim(),
      }))
    }
  }

  const handleFollowupClick = (text: string) => {
    void send(text)
  }

  const retry = () => {
    if (state.pendingText) {
      void send(state.pendingText)
    }
  }

  return (
    <div className="container flex h-[calc(100vh-4rem)] flex-col py-6">
      <PageHeader
        title="Trợ lý AI"
        description="Hỏi đáp về nghề nghiệp, kỹ năng và tin tuyển dụng — được trả lời dựa trên dữ liệu thực tế của nền tảng."
      />

      <div className="flex flex-1 flex-col overflow-hidden rounded-xl border bg-card/40">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {state.messages.length === 0 && !state.isLoading ? (
            <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
              <div className="ai-gradient flex h-14 w-14 items-center justify-center rounded-full text-white">
                <Bot className="h-7 w-7" aria-hidden="true" />
              </div>
              <div className="space-y-2">
                <p className="text-lg font-semibold">
                  Bắt đầu hội thoại với trợ lý AI
                </p>
                <p className="max-w-md text-sm text-muted-foreground">
                  Đặt câu hỏi về lộ trình nghề nghiệp, kỹ năng cần thiết hoặc
                  tin tuyển dụng. Trợ lý AI sẽ trả lời dựa trên dữ liệu của
                  nền tảng.
                </p>
              </div>
              <div className="flex max-w-lg flex-wrap justify-center gap-2">
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => void send(prompt)}
                    className="rounded-full border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    <Sparkles
                      className="mr-1 inline h-3.5 w-3.5 text-primary"
                      aria-hidden="true"
                    />
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {state.messages.map((item, index) => (
            <ChatMessageBubble
              key={`${item.message.role}-${index}`}
              message={item.message}
              sources={item.sources}
              suggestedFollowups={item.suggestedFollowups}
              onFollowupClick={handleFollowupClick}
            />
          ))}

          {state.isLoading ? (
            <div className="flex w-full items-center gap-3">
              <div className="ai-gradient flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white">
                <Bot className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="flex items-center gap-3 rounded-2xl rounded-tl-sm border bg-card px-4 py-3 text-sm text-muted-foreground">
                <Spinner size="sm" />
                <span>AI đang trả lời...</span>
              </div>
            </div>
          ) : null}

          {state.error ? (
            <div className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
              <p role="alert" className="flex-1 text-sm text-destructive">
                {state.error}
              </p>
              <Button variant="outline" size="sm" onClick={retry}>
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                Thử lại
              </Button>
            </div>
          ) : null}

          <div ref={bottomRef} />
        </div>

        <div className="border-t p-4">
          <ChatInput onSend={(text) => void send(text)} disabled={state.isLoading} />
        </div>
      </div>
    </div>
  )
}
