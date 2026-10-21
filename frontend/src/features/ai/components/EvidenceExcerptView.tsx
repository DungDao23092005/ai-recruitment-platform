import { useId, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/utils/cn'
import type { EvidenceExcerpt } from '@/types/ai'

const SECTION_LABELS: Record<string, string> = {
  skills: 'Kỹ năng',
  experiences: 'Kinh nghiệm',
  projects: 'Dự án',
  summary: 'Giới thiệu',
  education: 'Học vấn',
}

export function evidenceSectionLabel(section: string): string {
  return SECTION_LABELS[section] ?? section
}

const COLLAPSE_THRESHOLD = 220

export interface EvidenceExcerptViewProps {
  excerpt: EvidenceExcerpt
  className?: string
}

export function EvidenceExcerptView({
  excerpt,
  className,
}: EvidenceExcerptViewProps) {
  const quoteId = useId()
  const [expanded, setExpanded] = useState(false)
  const quote = excerpt.quote ?? ''
  const isCollapsible = quote.length > COLLAPSE_THRESHOLD
  const isCollapsed = isCollapsible && !expanded

  return (
    <figure
      className={cn('rounded-lg border bg-muted/20 px-3 py-2.5', className)}
    >
      <figcaption className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Badge variant="neutral" className="font-medium">
          {evidenceSectionLabel(excerpt.section)}
        </Badge>
        {excerpt.item_title ? (
          <span
            className="max-w-full truncate text-xs font-medium text-foreground"
            title={excerpt.item_title}
          >
            {excerpt.item_title}
          </span>
        ) : null}
        {excerpt.field_name ? (
          <span className="truncate text-xs text-muted-foreground">
            {excerpt.field_name}
          </span>
        ) : null}
      </figcaption>

      <blockquote
        id={quoteId}
        className={cn(
          'mt-2 border-l-2 border-primary/30 pl-3 text-sm italic leading-relaxed text-foreground/90',
          isCollapsed && 'line-clamp-3',
        )}
      >
        {quote}
      </blockquote>

      {isCollapsible ? (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
          aria-controls={quoteId}
          className="mt-2 inline-flex items-center gap-1 rounded text-xs font-medium text-primary transition-colors hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
        >
          <ChevronDown
            className={cn(
              'h-3.5 w-3.5 transition-transform',
              expanded && 'rotate-180',
            )}
            aria-hidden="true"
          />
          {expanded ? 'Thu gọn dẫn chứng' : 'Xem toàn bộ dẫn chứng'}
        </button>
      ) : null}
    </figure>
  )
}
