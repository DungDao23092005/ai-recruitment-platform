import * as React from 'react'
import { cn } from '@/utils/cn'

export interface ScoreRingProps {
  value: number
  size?: number
  strokeWidth?: number
  className?: string
  label?: string
}

export function ScoreRing({
  value,
  size = 72,
  strokeWidth = 6,
  className,
  label,
}: ScoreRingProps) {
  const id = React.useId()
  const clamped = Math.max(0, Math.min(100, Math.round(value)))
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (clamped / 100) * circumference
  const gradientId = `score-ring-${id.replace(/[:]/g, '')}`

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
          strokeDashoffset={offset}
        />
      </svg>
      <span
        className="absolute font-display font-bold text-foreground"
        style={{ fontSize: size / 3.6 }}
      >
        {clamped}
        <span className="text-[0.55em] font-semibold text-muted-foreground">
          %
        </span>
      </span>
    </div>
  )
}