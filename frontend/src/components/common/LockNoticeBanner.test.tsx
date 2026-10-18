import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { LockNoticeBanner } from './LockNoticeBanner'
import {
  LOCK_NOTICE_FALLBACK_REASON,
  formatLockNotice,
  getLockNotice,
  storeLockNotice,
} from '@/utils/lockNotice'

const LOCK_HEADING = 'Tài khoản của bạn đã bị khóa.'
const LOCK_REASON_LABEL = 'Lý do khóa tài khoản'

beforeEach(() => {
  localStorage.clear()
})

describe('LockNoticeBanner', () => {
  it('renders nothing when there is no pending notice', () => {
    const { container } = render(<LockNoticeBanner />)

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('renders a clear accessible heading when a notice is pending', () => {
    storeLockNotice(formatLockNotice('Vi phạm điều khoản'))

    render(<LockNoticeBanner />)

    expect(
      screen.getByRole('heading', { name: LOCK_HEADING }),
    ).toBeInTheDocument()
  })

  it('shows the actual reason in its own labeled section', () => {
    storeLockNotice(formatLockNotice('Vi phạm điều khoản'))

    render(<LockNoticeBanner />)

    const label = screen.getByText(LOCK_REASON_LABEL)
    const reason = screen.getByText('Vi phạm điều khoản.')
    expect(label.parentElement).toContainElement(reason)
  })

  it('shows the support instruction', () => {
    storeLockNotice(formatLockNotice('Vi phạm điều khoản'))

    render(<LockNoticeBanner />)

    expect(screen.getByText(LOCK_NOTICE_FALLBACK_REASON)).toBeInTheDocument()
  })

  it('uses a light-red surface with dark-red text for sufficient contrast', () => {
    storeLockNotice(formatLockNotice('Vi phạm điều khoản'))

    render(<LockNoticeBanner />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveClass('bg-red-50')
    expect(alert).toHaveClass('text-red-900')
    expect(alert).toHaveClass('border-red-200')
    // The reason text itself must be dark red, never white-on-pale-red.
    expect(screen.getByText('Vi phạm điều khoản.')).toHaveClass('text-red-900')
  })

  it('renders HTML-like reasons as plain text, never as HTML', () => {
    storeLockNotice(formatLockNotice('<script>alert(1)</script>'))

    render(<LockNoticeBanner />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('<script>alert(1)</script>')
    expect(alert.querySelector('script')).toBeNull()
  })

  it('keeps the full lock message content visible', () => {
    // The substantive content of the formatted message stays displayed even
    // though the heading, reason and support copy are now separate elements.
    storeLockNotice(formatLockNotice('Vi phạm điều khoản'))

    render(<LockNoticeBanner />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(LOCK_HEADING)
    expect(alert).toHaveTextContent(LOCK_REASON_LABEL)
    expect(alert).toHaveTextContent('Vi phạm điều khoản')
    expect(alert).toHaveTextContent(LOCK_NOTICE_FALLBACK_REASON)
  })

  it('consumes the one-time notice after rendering it', () => {
    storeLockNotice(formatLockNotice('Vi phạm điều khoản'))
    expect(getLockNotice()).not.toBeNull()

    render(<LockNoticeBanner />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(getLockNotice()).toBeNull()
  })

  it('falls back to the support copy when only the generic notice is stored', () => {
    storeLockNotice(formatLockNotice('   '))

    render(<LockNoticeBanner />)

    const alert = screen.getByRole('alert')
    // The fallback sentence appears once as the reason and once as the support line.
    expect(screen.getAllByText(LOCK_NOTICE_FALLBACK_REASON)).toHaveLength(2)
    expect(alert).toHaveTextContent(LOCK_HEADING)
  })

  it('applies an external className to the banner layout wrapper', () => {
    storeLockNotice(formatLockNotice('Vi phạm điều khoản'))

    const { container } = render(<LockNoticeBanner className="custom-wrapper" />)

    const wrapper = container.firstElementChild
    expect(wrapper).toHaveClass('container')
    expect(wrapper).toHaveClass('custom-wrapper')
  })
})
