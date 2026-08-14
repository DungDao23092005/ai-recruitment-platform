import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ChatInput } from './ChatInput'

describe('ChatInput', () => {
  it('renders textarea and send button', () => {
    render(<ChatInput onSend={vi.fn()} />)

    expect(screen.getByLabelText('Tin nhắn chat')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Gửi/i })).toBeInTheDocument()
  })

  it('sends typed message and clears input', () => {
    const onSend = vi.fn()

    render(<ChatInput onSend={onSend} />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Xin chào trợ lý' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Gửi/i }))

    expect(onSend).toHaveBeenCalledWith('Xin chào trợ lý')
    expect(screen.getByLabelText('Tin nhắn chat')).toHaveValue('')
  })

  it('sends on Enter key', () => {
    const onSend = vi.fn()

    render(<ChatInput onSend={onSend} />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: 'Gửi bằng Enter' },
    })
    fireEvent.submit(screen.getByLabelText('Tin nhắn chat').closest('form')!)

    expect(onSend).toHaveBeenCalledWith('Gửi bằng Enter')
  })

  it('does not send empty or whitespace message', () => {
    const onSend = vi.fn()

    render(<ChatInput onSend={onSend} />)

    fireEvent.change(screen.getByLabelText('Tin nhắn chat'), {
      target: { value: '   ' },
    })
    fireEvent.submit(screen.getByLabelText('Tin nhắn chat').closest('form')!)

    expect(onSend).not.toHaveBeenCalled()
  })

  it('disables input while loading', () => {
    render(<ChatInput onSend={vi.fn()} disabled />)

    expect(screen.getByRole('button', { name: /Gửi/i })).toBeDisabled()
    expect(screen.getByLabelText('Tin nhắn chat')).toBeEnabled()
  })

  it('shows loading text when disabled', () => {
    render(<ChatInput onSend={vi.fn()} disabled />)

    expect(screen.getByText('Đang gửi...')).toBeInTheDocument()
  })
})
