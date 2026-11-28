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



interface PendingRequest {
  id: string
  text: string
  history: ChatMessage[]
  recommendedJobIds: string[]
  idempotencyKey: string
}

interface PageState {
  messages: DisplayMessage[]
  recommendedJobIds: string[]
  isLoading: boolean
  error: string | null
  pendingRequest: PendingRequest | null
}

export function AIChatPage() {
  const [state, setState] = useState<PageState>({
    messages: [],
    recommendedJobIds: [],
    isLoading: false,
    error: null,
    pendingRequest: null,
  })

  const bottomRef = useRef<HTMLDivElement | null>(null)

  const messagesContainerRef = useRef<HTMLDivElement | null>(null)

  const isLoadingRef = useRef(false)



  const scrollToBottom = () => {

    const container = messagesContainerRef.current

    if (container) {

      container.scrollTo({

        top: container.scrollHeight,

        behavior: 'smooth',

      })

    }

  }



  useEffect(() => {

    scrollToBottom()

  }, [state.messages, state.isLoading])



  const send = async (text: string, isRetry = false) => {
    if (!text.trim() || isLoadingRef.current) {
      return
    }

    isLoadingRef.current = true

    let messageText: string
    let history: ChatMessage[]
    let requestRecommendedJobIds: string[]
    let idempotencyKey: string
    let currentPending: PendingRequest

    if (!isRetry) {
      messageText = text.trim()
      const userMessage: ChatMessage = { role: 'user', content: messageText }
      history = state.messages.slice(-10).map((item) => item.message)
      requestRecommendedJobIds = state.recommendedJobIds
      const messageId = crypto.randomUUID()
      idempotencyKey = `chat_${messageId}`
      currentPending = {
        id: messageId,
        text: messageText,
        history,
        recommendedJobIds: requestRecommendedJobIds,
        idempotencyKey,
      }

      setState((prev) => ({
        ...prev,
        messages: [
          ...prev.messages,
          { message: userMessage, sources: [], suggestedFollowups: [] },
        ],
        isLoading: true,
        error: null,
        pendingRequest: currentPending,
      }))
    } else {
      if (!state.pendingRequest) {
        isLoadingRef.current = false
        return
      }
      currentPending = state.pendingRequest
      messageText = currentPending.text
      history = currentPending.history
      requestRecommendedJobIds = currentPending.recommendedJobIds
      idempotencyKey = currentPending.idempotencyKey

      setState((prev) => ({
        ...prev,
        isLoading: true,
        error: null,
      }))
    }

    try {
      const response = await sendChatMessage(
        {
          message: messageText,
          history,
          ...(requestRecommendedJobIds.length > 0
            ? { recommended_job_ids: requestRecommendedJobIds }
            : {}),
        },
        idempotencyKey,
      )
      setState((prev) => {
        const nextRecommendedJobIds =
          response.recommended_job_ids && response.recommended_job_ids.length > 0
            ? Array.from(
                new Set([
                  ...prev.recommendedJobIds,
                  ...response.recommended_job_ids,
                ]),
              )
            : prev.recommendedJobIds
        const assistantMessage: DisplayMessage = {
          message: {
            role: 'assistant',
            content: response.answer,
            ...(response.recommended_job_ids &&
            response.recommended_job_ids.length > 0
              ? { recommended_job_ids: response.recommended_job_ids }
              : {}),
          },
          sources: response.sources,
          suggestedFollowups: response.suggested_followups,
        }
        return {
          ...prev,
          messages: [...prev.messages, assistantMessage],
          recommendedJobIds: nextRecommendedJobIds,
          isLoading: false,
          error: null,
          pendingRequest: null,
        }
      })
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: getFriendlyErrorMessage(err),
        pendingRequest: currentPending,
      }))
    } finally {
      isLoadingRef.current = false
    }
  }

  const retry = () => {
    if (state.pendingRequest) {
      void send(state.pendingRequest.text, true)
    }
  }

  const handleFollowupClick = (text: string) => {
    void send(text)
  }



return (

  <div className="flex h-[calc(100dvh-7rem)] flex-col sm:h-[calc(100dvh-8rem)]">

    <PageHeader

      title="Trợ lý AI tuyển dụng"

      description="Đặt câu hỏi về việc làm, ứng viên và tuyển dụng — được trả lời dựa trên dữ liệu thực tế của nền tảng."

    />



    <div className="flex flex-1 flex-col overflow-hidden rounded-xl border bg-card/40">

      <div

        ref={messagesContainerRef}

        className="flex-1 space-y-4 overflow-y-auto p-4"

      >

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