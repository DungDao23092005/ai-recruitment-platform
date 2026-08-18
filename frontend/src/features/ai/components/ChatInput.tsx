import { useState, type FormEvent } from 'react'
import { SendHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

export interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Nhập tin nhắn cho trợ lý AI...',
}: ChatInputProps) {
  const [value, setValue] = useState('')

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = value.trim()
    if (!trimmed || disabled) {
      return
    }
    onSend(trimmed)
    setValue('')
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <Textarea
        name="chat-message"
        rows={1}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        aria-label="Tin nhắn chat"
        className="max-h-40 min-h-0 flex-1 resize-none"
      />
      <Button
        type="submit"
        disabled={disabled || !value.trim()}
        isLoading={disabled}
        loadingText="Đang gửi..."
      >
        <SendHorizontal className="h-4 w-4" aria-hidden="true" />
        Gửi
      </Button>
    </form>
  )
}