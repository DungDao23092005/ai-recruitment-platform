import { CheckCircle2, Circle, Undo2, XCircle, type LucideIcon } from 'lucide-react'
import { cn } from '@/utils/cn'
import { getCandidateStage } from '@/types/application'
import type { ApplicationStatus, CandidateStage } from '@/types/application'

interface TrackerStep {
  stage: CandidateStage
  label: string
}

const STEPS: TrackerStep[] = [
  { stage: 'applied', label: 'Nộp hồ sơ' },
  { stage: 'under_review', label: 'Xem xét hồ sơ' },
  { stage: 'interviewing', label: 'Phỏng vấn' },
  { stage: 'offered', label: 'Đề nghị nhận việc' },
  { stage: 'outcome', label: 'Kết quả' },
]

type OutcomeTone = 'success' | 'destructive' | 'neutral'

interface OutcomeConfig {
  label: string
  tone: OutcomeTone
  icon: LucideIcon
}

const OUTCOME_CONFIG: Partial<Record<ApplicationStatus, OutcomeConfig>> = {
  accepted: { label: 'Đã chấp nhận', tone: 'success', icon: CheckCircle2 },
  rejected: { label: 'Từ chối', tone: 'destructive', icon: XCircle },
  withdrawn: { label: 'Đã rút đơn', tone: 'neutral', icon: Undo2 },
}

const OUTCOME_TONE_CLASSES: Record<OutcomeTone, string> = {
  success: 'border-success/30 bg-success/10 text-success',
  destructive: 'border-destructive/30 bg-destructive/10 text-destructive',
  neutral: 'border-foreground/20 bg-foreground/10 text-foreground',
}

export interface CandidateStatusTrackerProps {
  status: ApplicationStatus
  className?: string
}

export function CandidateStatusTracker({
  status,
  className,
}: CandidateStatusTrackerProps) {
  const stage = getCandidateStage(status)
  const currentIndex = STEPS.findIndex((step) => step.stage === stage)
  const isTerminal = stage === 'outcome'
  const outcome = OUTCOME_CONFIG[status]

  return (
    <div
      role="group"
      aria-label="Tiến trình ứng tuyển"
      className={cn('w-full', className)}
    >
      <ol className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-1">
        {STEPS.map((step, index) => {
          const isCurrent = index === currentIndex
          const isCompleted = !isTerminal && index < currentIndex
          const isOutcomeStep = step.stage === 'outcome'
          const label = isOutcomeStep && outcome ? outcome.label : step.label
          const Icon = isOutcomeStep && outcome
            ? outcome.icon
            : isCompleted
              ? CheckCircle2
              : Circle
          const stateLabel = isCurrent
            ? 'Bước hiện tại'
            : isCompleted
              ? 'Đã hoàn thành'
              : 'Chưa bắt đầu'

          return (
            <li
              key={step.stage}
              aria-current={isCurrent ? 'step' : undefined}
              className="flex flex-1 items-center gap-2"
            >
              <span
                className={cn(
                  'flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-colors',
                  isCompleted && 'border-success/30 bg-success/10 text-success',
                  isCurrent &&
                    (isOutcomeStep && outcome
                      ? OUTCOME_TONE_CLASSES[outcome.tone]
                      : 'border-primary/30 bg-primary/10 text-primary'),
                  !isCompleted &&
                    !isCurrent &&
                    'border-border bg-muted text-muted-foreground',
                )}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
              <span
                className={cn(
                  'text-xs font-medium',
                  isCurrent ? 'text-foreground' : 'text-muted-foreground',
                )}
              >
                {label}
              </span>
              <span className="sr-only">{stateLabel}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
