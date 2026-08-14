import { Fragment, type Key, type ReactNode } from 'react'
import { Bot, User, Sparkles } from 'lucide-react'
import { cn } from '@/utils/cn'
import { Badge } from '@/components/ui/badge'
import type { ChatMessage, ChatSource } from '@/types/ai'

export interface ChatMessageBubbleProps {
  message: ChatMessage
  sources?: ChatSource[]
  suggestedFollowups?: string[]
  onFollowupClick?: (text: string) => void
}

export function formatSourceScore(score: number): string {
  if (Number.isNaN(score)) {
    return '0%'
  }
  return `${Math.round(score * 100)}%`
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g
  const parts = text.split(pattern)
  for (const part of parts) {
    if (!part) {
      continue
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      nodes.push(<strong key={part}>{part.slice(2, -2)}</strong>)
    } else if (part.startsWith('`') && part.endsWith('`')) {
      nodes.push(
        <code key={part} className="rounded bg-secondary px-1 py-0.5 text-sm">
          {part.slice(1, -1)}
        </code>,
      )
    } else {
      nodes.push(<Fragment key={part}>{part}</Fragment>)
    }
  }
  return nodes
}

function renderLine(line: string, key: Key): ReactNode {
  if (line.startsWith('### ')) {
    return (
      <h4 key={key} className="mt-2 text-sm font-semibold">
        {renderInline(line.slice(4))}
      </h4>
    )
  }
  if (line.startsWith('## ')) {
    return (
      <h3 key={key} className="mt-2 text-base font-semibold">
        {renderInline(line.slice(3))}
      </h3>
    )
  }
  if (line.startsWith('# ')) {
    return (
      <h2 key={key} className="mt-2 text-lg font-semibold">
        {renderInline(line.slice(2))}
      </h2>
    )
  }
  if (line.startsWith('- ') || line.startsWith('* ')) {
    return (
      <li key={key} className="ml-4 list-disc">
        {renderInline(line.slice(2))}
      </li>
    )
  }
  return <p key={key}>{renderInline(line)}</p>
}

export function renderMarkdown(text: string): ReactNode {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let listBuffer: string[] = []

  const flushList = (keyBase: string) => {
    if (listBuffer.length > 0) {
      blocks.push(
        <ul key={keyBase} className="space-y-0.5">
          {listBuffer.map((item, i) => renderLine(item, i))}
        </ul>,
      )
      listBuffer = []
    }
  }

  lines.forEach((line, index) => {
    const isListItem = line.startsWith('- ') || line.startsWith('* ')
    if (isListItem) {
      listBuffer.push(line)
      return
    }
    flushList(`list-${index}`)
    if (line.trim() === '') {
      return
    }
    blocks.push(renderLine(line, `line-${index}`))
  })
  flushList('list-final')

  return <div className="space-y-1">{blocks}</div>
}

export function ChatMessageBubble({
  message,
  sources,
  suggestedFollowups,
  onFollowupClick,
}: ChatMessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={cn('flex w-full gap-3', isUser ? 'justify-end' : 'justify-start')}
    >
      {!isUser ? (
        <div className="ai-gradient flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </div>
      ) : null}

      <div className={cn('max-w-[80%] space-y-2', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'rounded-2xl border px-4 py-3 text-sm leading-relaxed',
            isUser
              ? 'rounded-tr-sm bg-primary text-primary-foreground'
              : 'rounded-tl-sm bg-card text-card-foreground',
          )}
        >
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            renderMarkdown(message.content)
          )}
        </div>

        {!isUser && sources && sources.length > 0 ? (
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Nguồn tham khảo
            </p>
            {sources.map((source) => (
              <div
                key={source.entity_id}
                className="flex items-start justify-between gap-3 rounded-lg border bg-card/60 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium">{source.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {source.source_type === 'job' ? 'Tin tuyển dụng' : 'Hồ sơ ứng viên'}
                    {source.skills.length > 0
                      ? ` · ${source.skills.join(', ')}`
                      : ''}
                  </p>
                </div>
                <Badge
                  variant="neutral"
                  className="shrink-0 text-xs font-bold"
                  aria-label={`Relevance score ${formatSourceScore(source.relevance_score)}`}
                >
                  {formatSourceScore(source.relevance_score)}
                </Badge>
              </div>
            ))}
          </div>
        ) : null}

        {!isUser && suggestedFollowups && suggestedFollowups.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {suggestedFollowups.map((followup) => (
              <button
                key={followup}
                type="button"
                onClick={() => onFollowupClick?.(followup)}
                className="rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                {followup}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {isUser ? (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
          <User className="h-4 w-4" aria-hidden="true" />
        </div>
      ) : null}
    </div>
  )
}
