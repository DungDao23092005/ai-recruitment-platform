import { useEffect, useState } from 'react'
import { ErrorBanner } from '@/components/ui/error-banner'
import { consumeLockNotice, getLockNotice } from '@/utils/lockNotice'

/**
 * One-time notice shown on the public homepage after an account was locked
 * while it was in use. The message is read (not removed) during the initial
 * render so it is visible on first paint, then consumed once mounted so it is
 * shown exactly once.
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

  return <ErrorBanner message={message} className={className} />
}
