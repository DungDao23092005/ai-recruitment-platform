import type { ElementType } from 'react'
import { CheckCircle2, CircleDashed, CircleHelp } from 'lucide-react'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { cn } from '@/utils/cn'
import { EvidenceExcerptView } from './EvidenceExcerptView'
import type { ExperienceEvaluation } from '@/types/ai'

interface ExperienceRelevanceMeta {
  label: string
  variant: NonNullable<BadgeProps['variant']>
  Icon: ElementType
  iconClassName: string
}

const RELEVANCE_META: Record<string, ExperienceRelevanceMeta> = {
  relevant_skills: {
    label: 'Sử dụng kỹ năng yêu cầu',
    variant: 'success',
    Icon: CheckCircle2,
    iconClassName: 'text-success',
  },
  no_required_skill_overlap: {
    label: 'Chưa thấy kỹ năng yêu cầu',
    variant: 'neutral',
    Icon: CircleDashed,
    iconClassName: 'text-muted-foreground',
  },
  no_overlap_with_requirements: {
    label: 'Chưa thấy kỹ năng yêu cầu',
    variant: 'neutral',
    Icon: CircleDashed,
    iconClassName: 'text-muted-foreground',
  },
  no_requirement_to_compare: {
    label: 'Không có yêu cầu để đối chiếu',
    variant: 'info',
    Icon: CircleHelp,
    iconClassName: 'text-info',
  },
}

export function getExperienceRelevanceMeta(
  relevance: string,
): ExperienceRelevanceMeta {
  return (
    RELEVANCE_META[relevance] ?? {
      label: relevance,
      variant: 'neutral',
      Icon: CircleDashed,
      iconClassName: 'text-muted-foreground',
    }
  )
}

const NO_EXPERIENCE_MESSAGE = 'Chưa có kinh nghiệm để đối chiếu.'
const NO_TITLE_MESSAGE = 'Chưa có thông tin chức danh'

function ExperienceCard({ evaluation }: { evaluation: ExperienceEvaluation }) {
  const meta = getExperienceRelevanceMeta(evaluation.relevance)
  const { Icon } = meta
  const heading = [evaluation.role_title, evaluation.company]
    .filter((value): value is string => Boolean(value))
    .join(' · ')

  return (
    <li className="rounded-lg border bg-card px-3.5 py-3">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <div className="min-w-0">
          <p
            className={cn(
              'break-words text-sm font-semibold',
              heading ? 'text-foreground' : 'text-muted-foreground',
            )}
          >
            {heading || NO_TITLE_MESSAGE}
          </p>
          {evaluation.duration ? (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {evaluation.duration}
            </p>
          ) : null}
        </div>
        <Badge variant={meta.variant} className="shrink-0">
          <Icon
            className={cn('mr-1 h-3.5 w-3.5', meta.iconClassName)}
            aria-hidden="true"
          />
          {meta.label}
        </Badge>
      </div>

      {evaluation.explanation ? (
        <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
          {evaluation.explanation}
        </p>
      ) : null}

      {evaluation.evidence.length > 0 ? (
        <div className="mt-2.5 space-y-2">
          {evaluation.evidence.map((excerpt, index) => (
            <EvidenceExcerptView
              key={`experience-${index}`}
              excerpt={excerpt}
            />
          ))}
        </div>
      ) : null}
    </li>
  )
}

export interface ExperienceEvaluationListProps {
  evaluations: ExperienceEvaluation[]
  className?: string
}

export function ExperienceEvaluationList({
  evaluations,
  className,
}: ExperienceEvaluationListProps) {
  if (evaluations.length === 0) {
    return (
      <p
        className={cn(
          'rounded-lg border border-dashed bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground',
          className,
        )}
      >
        {NO_EXPERIENCE_MESSAGE}
      </p>
    )
  }

  return (
    <ul className={cn('space-y-3', className)}>
      {evaluations.map((evaluation, index) => (
        <ExperienceCard key={`experience-${index}`} evaluation={evaluation} />
      ))}
    </ul>
  )
}
