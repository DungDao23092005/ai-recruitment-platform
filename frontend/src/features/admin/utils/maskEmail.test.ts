import { describe, expect, it } from 'vitest'
import { maskEmail } from '@/features/admin/utils/maskEmail'

describe('maskEmail', () => {
  it('masks a valid address while preserving the domain', () => {
    expect(maskEmail('buyer@example.com')).toBe('b***@example.com')
  })

  it('masks a single-character local part', () => {
    expect(maskEmail('a@example.com')).toBe('a***@example.com')
  })

  it('preserves subdomains', () => {
    expect(maskEmail('user@mail.example.com')).toBe('u***@mail.example.com')
  })

  it('returns an empty string for blank and nullish values', () => {
    expect(maskEmail(null)).toBe('')
    expect(maskEmail(undefined)).toBe('')
    expect(maskEmail('')).toBe('')
    expect(maskEmail('   ')).toBe('')
  })

  it('never exposes malformed input', () => {
    const malformed = [
      'buyer.example.com',
      'buyer@@example.com',
      'buyer@example',
      '@example.com',
      'buyer@',
      'buyer @example.com',
    ]

    for (const value of malformed) {
      const masked = maskEmail(value)
      expect(masked).toBe('***')
      expect(masked).not.toContain('buyer')
      expect(masked).not.toContain(value)
    }
  })
})
