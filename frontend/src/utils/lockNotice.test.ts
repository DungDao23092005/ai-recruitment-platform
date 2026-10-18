import { describe, expect, it, beforeEach } from 'vitest'
import {
  LOCK_NOTICE_FALLBACK_REASON,
  LOCK_NOTICE_STORAGE_KEY,
  consumeLockNotice,
  formatLockNotice,
  getLockNotice,
  hasPendingLockNotice,
  storeLockNotice,
} from './lockNotice'

beforeEach(() => {
  localStorage.clear()
})

describe('formatLockNotice', () => {
  it('includes the real lock reason', () => {
    expect(formatLockNotice('Vi phạm điều khoản')).toBe(
      'Tài khoản của bạn đã bị khóa. Lý do: Vi phạm điều khoản.',
    )
  })

  it('falls back when the reason is missing or blank', () => {
    const expected = `Tài khoản của bạn đã bị khóa. Lý do: ${LOCK_NOTICE_FALLBACK_REASON}`
    expect(formatLockNotice(undefined)).toBe(expected)
    expect(formatLockNotice(null)).toBe(expected)
    expect(formatLockNotice('   ')).toBe(expected)
  })

  it('does not double the sentence terminator when the reason already ends with one', () => {
    expect(formatLockNotice('Vi phạm điều khoản.')).toBe(
      'Tài khoản của bạn đã bị khóa. Lý do: Vi phạm điều khoản.',
    )
  })
})

describe('lock notice storage', () => {
  it('stores, reads and consumes the message exactly once', () => {
    storeLockNotice('notice')
    expect(hasPendingLockNotice()).toBe(true)
    expect(getLockNotice()).toBe('notice')
    expect(consumeLockNotice()).toBe('notice')
    expect(getLockNotice()).toBeNull()
    expect(consumeLockNotice()).toBeNull()
  })

  it('keeps the first stored notice (specific reason wins over fallback)', () => {
    storeLockNotice('specific')
    storeLockNotice('generic')
    expect(getLockNotice()).toBe('specific')
  })

  it('ignores an empty message', () => {
    storeLockNotice('')
    expect(getLockNotice()).toBeNull()
  })

  it('exposes the storage key used for cross-tab convergence', () => {
    storeLockNotice('notice')
    expect(localStorage.getItem(LOCK_NOTICE_STORAGE_KEY)).toBe('notice')
  })
})
