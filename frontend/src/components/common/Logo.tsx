import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { cn } from '@/utils/cn'

export interface LogoProps {
  className?: string
  to?: string
  variant?: 'default' | 'light'
}

export function Logo({ className, to = '/', variant = 'default' }: LogoProps) {
  const content = (
    <span className={cn('flex items-center gap-2.5', className)}>
      <span className="ai-gradient flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white shadow-ai">
        <Sparkles className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="flex flex-col leading-none">
        <span
          className={cn(
            'font-display text-base font-bold tracking-tight',
            variant === 'light' ? 'text-white' : 'text-foreground',
          )}
        >
          Tuyển Dụng <span className="ai-text">AI</span>
        </span>
        <span
          className={cn(
            'mt-0.5 text-[10px] font-medium uppercase tracking-[0.14em]',
            variant === 'light' ? 'text-white/70' : 'text-muted-foreground',
          )}
        >
          Recruitment Platform
        </span>
      </span>
    </span>
  )

  return (
    <Link
      to={to}
      className="shrink-0"
      aria-label="Tuyển Dụng AI — Trang chủ"
    >
      {content}
    </Link>
  )
}
