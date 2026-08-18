import { Badge, type BadgeProps } from '@/components/ui/badge'
import type { ApplicationStatus } from '@/types/application'

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: 'Đã nộp',
  under_review: 'Đang xem xét',
  shortlisted: 'Lọt vòng ngắn',
  interviewing: 'Đang phỏng vấn',
  accepted: 'Đã chấp nhận',
  rejected: 'Từ chối',
  withdrawn: 'Đã rút',
}

const STATUS_VARIANTS: Record<ApplicationStatus, BadgeProps['variant']> = {
  applied: 'neutral',
  under_review: 'info',
  shortlisted: 'outline-ai',
  interviewing: 'warning',
  accepted: 'success',
  rejected: 'destructive',
  withdrawn: 'neutral',
}

export function ApplicationStatusBadge({
  status,
  className,
}: {
  status: ApplicationStatus
  className?: string
}) {
  return (
    <Badge variant={STATUS_VARIANTS[status]} className={className}>
      {APPLICATION_STATUS_LABELS[status]}
    </Badge>
  )
}