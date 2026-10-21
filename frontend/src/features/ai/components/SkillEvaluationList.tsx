import type { ElementType } from 'react'
import { CheckCircle2, CircleDashed, CircleHelp, Lightbulb } from 'lucide-react'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { cn } from '@/utils/cn'
import { EvidenceExcerptView } from './EvidenceExcerptView'
import type { SkillEvaluation, SkillMatchStatus } from '@/types/ai'

interface SkillStatusMeta {
  label: string
  variant: NonNullable<BadgeProps['variant']>
  Icon: ElementType
  iconClassName: string
  neutralNote?: string
}

export const SKILL_STATUS_META: Record<SkillMatchStatus, SkillStatusMeta> = {
  matched_evidenced: {
    label: 'Đã đối soát trong CV',
    variant: 'success',
    Icon: CheckCircle2,
    iconClassName: 'text-success',
  },
  partially_matched: {
    label: 'Khớp một phần',
    variant: 'warning',
    Icon: Lightbulb,
    iconClassName: 'text-warning',
  },
  not_evidenced_in_cv: {
    label: 'Chưa thấy dẫn chứng trong CV',
    variant: 'neutral',
    Icon: CircleDashed,
    iconClassName: 'text-muted-foreground',
    neutralNote:
      'Không tìm thấy thông tin trong CV được cung cấp; điều này không khẳng định ứng viên thiếu kỹ năng này.',
  },
  insufficient_data: {
    label: 'Chưa đủ dữ liệu',
    variant: 'info',
    Icon: CircleHelp,
    iconClassName: 'text-info',
  },
}

export function groupSkillEvaluations(evaluations: SkillEvaluation[]): {
  required: SkillEvaluation[]
  preferred: SkillEvaluation[]
} {
  return {
    required: evaluations.filter((item) => item.requirement_type === 'required'),
    preferred: evaluations.filter(
      (item) => item.requirement_type === 'preferred',
    ),
  }
}

function SkillItem({ evaluation }: { evaluation: SkillEvaluation }) {
  const meta = SKILL_STATUS_META[evaluation.status]
  const { Icon } = meta

  return (
    <li className="rounded-lg border bg-card px-3.5 py-3">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <Icon
            className={cn('h-4 w-4 shrink-0', meta.iconClassName)}
            aria-hidden="true"
          />
          <span className="min-w-0 break-words text-sm font-semibold text-foreground">
            {evaluation.skill_name}
          </span>
        </div>
        <Badge
          variant={meta.variant}
          className="shrink-0"
          title={meta.neutralNote}
        >
          {meta.label}
        </Badge>
      </div>

      {evaluation.explanation ? (
        <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
          {evaluation.explanation}
        </p>
      ) : null}

      {meta.neutralNote ? (
        <p className="mt-1 text-xs text-muted-foreground">{meta.neutralNote}</p>
      ) : null}

      {evaluation.evidence.length > 0 ? (
        <div className="mt-2.5 space-y-2">
          {evaluation.evidence.map((excerpt, index) => (
            <EvidenceExcerptView
              key={`${evaluation.skill_name}-evidence-${index}`}
              excerpt={excerpt}
            />
          ))}
        </div>
      ) : null}
    </li>
  )
}

function SkillGroup({
  title,
  items,
  emptyLabel,
}: {
  title: string
  items: SkillEvaluation[]
  emptyLabel: string
}) {
  return (
    <section aria-label={title} className="space-y-2.5">
      <h4 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
        {items.length > 0 ? (
          <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[0.65rem] font-semibold text-secondary-foreground">
            {items.length}
          </span>
        ) : null}
      </h4>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((evaluation) => (
            <SkillItem
              key={`${evaluation.requirement_type}-${evaluation.skill_name}`}
              evaluation={evaluation}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

export interface SkillEvaluationListProps {
  evaluations: SkillEvaluation[]
  className?: string
}

export function SkillEvaluationList({
  evaluations,
  className,
}: SkillEvaluationListProps) {
  if (evaluations.length === 0) {
    return (
      <p
        className={cn(
          'rounded-lg border border-dashed bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground',
          className,
        )}
      >
        Chưa có đánh giá kỹ năng để hiển thị.
      </p>
    )
  }

  const { required, preferred } = groupSkillEvaluations(evaluations)

  return (
    <div className={cn('space-y-5', className)}>
      <SkillGroup
        title="Kỹ năng bắt buộc"
        items={required}
        emptyLabel="Không có kỹ năng bắt buộc."
      />
      <SkillGroup
        title="Kỹ năng ưu tiên"
        items={preferred}
        emptyLabel="Không có kỹ năng ưu tiên."
      />
    </div>
  )
}
