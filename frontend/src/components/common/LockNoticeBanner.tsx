import { useEffect, useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import { cn } from '@/utils/cn'
import {
  LOCK_NOTICE_FALLBACK_REASON,
  consumeLockNotice,
  getLockNotice,
} from '@/utils/lockNotice'

const LOCK_HEADING = 'Tài khoản của bạn đã bị khóa.'
const LOCK_REASON_LABEL = 'Lý do khóa tài khoản'
const LOCK_SUPPORT_MESSAGE = LOCK_NOTICE_FALLBACK_REASON

// `formatLockNotice` always produces `<heading> Lý do: <reason>.`; we recover the
// reason from the stored message so it can be shown in its own labeled section
// without changing the `lockNotice.ts` storage contract.
const REASON_PREFIX = 'Lý do: '

function extractLockReason(message: string): string {
  const prefixIndex = message.indexOf(REASON_PREFIX)
  if (prefixIndex === -1) {
    return message.trim()
  }
  // Keep the reason sentence intact, including its terminal period.
  return message.slice(prefixIndex + REASON_PREFIX.length).trim()
}

/**
 * One-time notice shown on the public homepage after an account was locked
 * while it was in use.
 *
 * The message is read (not removed) during the initial render so it is visible
 * on first paint, then consumed once mounted so it is shown exactly once. When
 * no notice is pending the component renders nothing at all, so no empty padded
 * wrapper is left behind on the homepage. Reasons are rendered as React text
 * nodes only (never `dangerouslySetInnerHTML`).
 */
export function LockNoticeBanner({ className }: { className?: string }) {
  const [message] = useState<string | null>(() => getLockNotice())

  useEffect(() => {
    if (message) {
      consumeLockNotice()
    }
  }, [message])

  if (!message) {
    return null
  }

  const reason = extractLockReason(message) || LOCK_SUPPORT_MESSAGE

  return (
    <div className={cn('container relative pt-6', className)}>
      <div
        role="alert"
        className="flex items-start gap-4 rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-red-900 shadow-soft sm:px-5"
      >
        <span
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-100 text-red-600"
          aria-hidden="true"
        >
          <ShieldAlert className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <h2 className="font-display text-base font-semibold text-red-900">
            {LOCK_HEADING}
          </h2>
          <div className="rounded-lg border border-red-200 bg-red-100/70 px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-red-700">
              {LOCK_REASON_LABEL}
            </p>
            <p className="mt-0.5 break-words text-sm font-medium text-red-900">
              {reason}
            </p>
          </div>
          <p className="text-sm text-red-800">{LOCK_SUPPORT_MESSAGE}</p>
        </div>
      </div>
    </div>
  )
}
