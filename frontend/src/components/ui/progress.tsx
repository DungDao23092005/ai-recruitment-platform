import * as React from 'react'
import { cn } from '@/utils/cn'

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number
  variant?: 'primary' | 'success' | 'warning' | 'danger' | 'ai'
}

const variantClasses: Record<NonNullable<ProgressProps['variant']>, string> = {
  primary: 'bg-primary',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-destructive',
  ai: 'ai-gradient',
}

export function Progress({
  value,
  variant = 'primary',
  className,
  ...props
}: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, value))

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
      className={cn('h-2 w-full overflow-hidden rounded-full bg-muted', className)}
      {...props}
    >
      <div
        className={cn('h-full rounded-full transition-all duration-500', variantClasses[variant])}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}