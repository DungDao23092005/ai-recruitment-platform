import * as React from 'react'
import { X } from 'lucide-react'
import { cn } from '@/utils/cn'
import { Button } from '@/components/ui/button'

export interface ModalProps {
  onClose: () => void
  title?: React.ReactNode
  description?: React.ReactNode
  ariaLabel?: string
  size?: 'sm' | 'md' | 'lg'
  children?: React.ReactNode
  footer?: React.ReactNode
}

export function Modal({
  onClose,
  title,
  description,
  ariaLabel,
  size = 'md',
  children,
  footer,
}: ModalProps) {
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
    >
      <div
        className="absolute inset-0 bg-foreground/40 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={cn(
          'relative z-10 max-h-[90vh] w-full animate-fade-in-up overflow-y-auto rounded-t-2xl border bg-card text-card-foreground shadow-soft-lg sm:rounded-2xl',
          size === 'sm' && 'sm:max-w-md',
          size === 'md' && 'sm:max-w-xl',
          size === 'lg' && 'sm:max-w-2xl',
        )}
      >
        {title || description ? (
          <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b bg-card px-5 py-4 sm:px-6">
            <div className="min-w-0">
              {title ? (
                <h2 className="font-display text-lg font-semibold text-foreground">
                  {title}
                </h2>
              ) : null}
              {description ? (
                <p className="mt-1 text-sm text-muted-foreground">
                  {description}
                </p>
              ) : null}
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={onClose}
              aria-label="Đóng"
              className="h-8 w-8 shrink-0"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        ) : null}
        <div className="px-5 py-4 sm:px-6">{children}</div>
        {footer ? (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/40 px-5 py-3 sm:px-6">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  )
}