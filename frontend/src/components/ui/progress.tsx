import * as React from 'react'
import { cn } from '@/utils/cn'

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number
  variant?: 'primary' | 'success' | 'warning' | 'danger' | 'ai'
  animate?: boolean
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
  animate = true,
  ...props
}: ProgressProps) {
  const [displayValue, setDisplayValue] = React.useState(0)
  const clamped = Math.max(0, Math.min(100, value))
  const shouldAnimate = animate

  React.useEffect(() => {
    if (!shouldAnimate) {
      setDisplayValue(clamped)
      return
    }

    if (typeof window === 'undefined' || !window.IntersectionObserver) {
      setDisplayValue(clamped)
      return
    }

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReducedMotion) {
      setDisplayValue(clamped)
      return
    }

    let animationFrame: number
    const startTime = Date.now()
    const duration = 1000

    const runAnimation = () => {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      const easedProgress = 1 - Math.pow(1 - progress, 3)
      setDisplayValue(Math.round(clamped * easedProgress))

      if (progress < 1) {
        animationFrame = requestAnimationFrame(runAnimation)
      } else {
        setDisplayValue(clamped)
      }
    }

    animationFrame = requestAnimationFrame(runAnimation)

    return () => {
      cancelAnimationFrame(animationFrame)
    }
  }, [clamped, shouldAnimate])

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
        style={{ width: `${displayValue}%` }}
      />
    </div>
  )
}