import * as React from 'react'
import { cn } from '@/utils/cn'

export interface ScoreRingProps {
  value: number
  size?: number
  strokeWidth?: number
  className?: string
  label?: string
  animate?: boolean
}

export function ScoreRing({
  value,
  size = 72,
  strokeWidth = 6,
  className,
  label,
  animate = true,
}: ScoreRingProps) {
  const id = React.useId()
  const [displayValue, setDisplayValue] = React.useState(0)
  const clamped = Math.max(0, Math.min(100, Math.round(value)))
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const gradientId = `score-ring-${id.replace(/[:]/g, '')}`
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

  const displayOffset = circumference - (displayValue / 100) * circumference

  return (
    <div
      className={cn('relative inline-flex items-center justify-center', className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label || `Điểm ${clamped} phần trăm`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient
            id={gradientId}
            x1="0%"
            y1="0%"
            x2="100%"
            y2="100%"
          >
            <stop offset="0%" stopColor="hsl(236 72% 47%)" />
            <stop offset="100%" stopColor="hsl(252 83% 54%)" />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={displayOffset}
          style={{
            transition: 'stroke-dashoffset 200ms ease-out',
          }}
        />
      </svg>
      <span
        className="absolute font-display font-bold text-foreground"
        style={{ fontSize: size / 3.6 }}
      >
        {displayValue}
        <span className="text-[0.55em] font-semibold text-muted-foreground">
          %
        </span>
      </span>
    </div>
  )
}