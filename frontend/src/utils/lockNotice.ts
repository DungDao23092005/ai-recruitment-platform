// One-time forced-logout notice shown on the public homepage after an admin
// locks an account that was in use.
//
// The message is stored in localStorage so overlapping tabs converge on the
// same notice and it survives the cross-tab logout redirect. It is consumed
// (removed) the first time it is displayed, so a stale notice can never appear
// again on a later visit.

export const LOCK_NOTICE_STORAGE_KEY = 'ai_recruitment_lock_notice'

export const LOCK_NOTICE_FALLBACK_REASON =
  'Vui lòng liên hệ quản trị viên để biết thêm thông tin.'

function resolveReason(reason?: string | null): string {
  const trimmed = typeof reason === 'string' ? reason.trim() : ''
  const base = trimmed || LOCK_NOTICE_FALLBACK_REASON
  // Drop any trailing whitespace/punctuation so the sentence terminator we add
  // below is never doubled (the fallback reason already ends with a period).
  return base.replace(/[.\s]+$/, '')
}

export function formatLockNotice(reason?: string | null): string {
  return `Tài khoản của bạn đã bị khóa. Lý do: ${resolveReason(reason)}.`
}

export function getLockNotice(): string | null {
  try {
    return localStorage.getItem(LOCK_NOTICE_STORAGE_KEY)
  } catch {
    return null
  }
}

export function hasPendingLockNotice(): boolean {
  return getLockNotice() !== null
}

export function storeLockNotice(message: string): void {
  if (!message) return
  try {
    // First notice wins: a precise SSE reason must never be overwritten by the
    // generic 403 fallback that may arrive from an in-flight request.
    if (!localStorage.getItem(LOCK_NOTICE_STORAGE_KEY)) {
      localStorage.setItem(LOCK_NOTICE_STORAGE_KEY, message)
    }
  } catch {
    // Storage unavailable (private mode, quota) - eviction still proceeds.
  }
}

export function consumeLockNotice(): string | null {
  const message = getLockNotice()
  if (message !== null) {
    try {
      localStorage.removeItem(LOCK_NOTICE_STORAGE_KEY)
    } catch {
      // ignore
    }
  }
  return message
}
