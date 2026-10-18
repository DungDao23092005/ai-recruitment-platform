import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { LockNoticeBanner } from './LockNoticeBanner'
import {
  formatLockNotice,
  getLockNotice,
  storeLockNotice,
} from '@/utils/lockNotice'

beforeEach(() => {
  localStorage.clear()
})

describe('LockNoticeBanner', () => {
  it('renders nothing when there is no pending notice', () => {
    const { container } = render(<LockNoticeBanner />)

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('renders the pending notice once and consumes it', () => {
    const message = formatLockNotice('Vi phạm điều khoản')
    storeLockNotice(message)

    render(<LockNoticeBanner />)

    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(getLockNotice()).toBeNull()
  })

  it('renders the reason as plain text, never as HTML', () => {
    storeLockNotice(formatLockNotice('<script>alert(1)</script>'))

    render(<LockNoticeBanner />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('<script>alert(1)</script>')
    expect(alert.querySelector('script')).toBeNull()
  })
})
