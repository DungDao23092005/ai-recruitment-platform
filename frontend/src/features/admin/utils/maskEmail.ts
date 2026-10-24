const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function maskEmail(value: string | null | undefined): string {
  if (typeof value !== 'string') return ''

  const trimmed = value.trim()
  if (!trimmed) return ''
  if (!EMAIL_PATTERN.test(trimmed)) return '***'

  const atIndex = trimmed.lastIndexOf('@')
  const local = trimmed.slice(0, atIndex)
  const domain = trimmed.slice(atIndex + 1)
  if (!local || !domain) return '***'

  return `${local[0]}***@${domain}`
}
