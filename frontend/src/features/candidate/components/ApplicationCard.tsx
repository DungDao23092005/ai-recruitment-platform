import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, ExternalLink, Undo2 } from 'lucide-react'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button, buttonVariants } from '@/components/ui/button'
import { ApplicationStatusBadge } from '@/components/common/ApplicationStatusBadge'
import { withdrawApplication } from '@/api/applications'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'
import type { ApplicationStatus, ApplicationWithJob } from '@/types/application'

export const WITHDRAWABLE_STATUSES: ApplicationStatus[] = [
  'applied',
  'under_review',
  'shortlisted',
  'interviewing',
]

export interface ApplicationCardProps {
  application: ApplicationWithJob
  detailPath?: string
  onWithdrawn?: (applicationId: string) => void
}

function formatAppliedDate(dateString: string): string {
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleDateString('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function companyMonogram(companyName: string): string {
  const trimmed = companyName.trim()
  if (!trimmed) {
    return 'C'
  }
  const words = trimmed.split(/\s+/)
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase()
  }
  return (
    words
      .slice(0, 2)
      .map((word) => word[0])
      .join('')
      .toUpperCase()
  )
}

export function ApplicationCard({
  application,
  detailPath = '/candidate/jobs',
  onWithdrawn,
}: ApplicationCardProps) {
  const { id, job_title, company_name, status, created_at } = application
  const [withdrawing, setWithdrawing] = useState(false)
  const [withdrawError, setWithdrawError] = useState<string | null>(null)

  const canWithdraw = WITHDRAWABLE_STATUSES.includes(status)
  const appliedDate = formatAppliedDate(created_at)
  const rawCompanyName = company_name ?? 'Công ty'
  const companyLabel = company_name ? `Công ty ${company_name}` : rawCompanyName

  const handleWithdraw = async () => {
    setWithdrawing(true)
    setWithdrawError(null)
    try {
      await withdrawApplication(id)
      onWithdrawn?.(id)
    } catch (err) {
      setWithdrawError(getFriendlyErrorMessage(err))
    } finally {
      setWithdrawing(false)
    }
  }

  return (
    <Card className="border-border/70 bg-card shadow-soft">
      <CardHeader className="gap-3">
        <div className="flex items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 font-display text-sm font-bold text-primary ring-1 ring-primary/15"
            aria-hidden="true"
          >
            {companyMonogram(rawCompanyName)}
          </div>
          <div className="min-w-0 flex-1">
            <CardTitle className="line-clamp-1 font-display text-lg font-semibold leading-snug text-foreground">
              {job_title}
            </CardTitle>
            <p className="mt-0.5 truncate text-sm text-muted-foreground">
              {companyLabel}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <ApplicationStatusBadge status={status} />
        </div>
        {appliedDate ? (
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <CalendarDays className="h-4 w-4 text-primary/70" aria-hidden="true" />
            Ứng tuyển: {appliedDate}
          </p>
        ) : null}
        {withdrawError ? (
          <p
            role="alert"
            className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
          >
            {withdrawError}
          </p>
        ) : null}
      </CardContent>
      <CardFooter className="flex flex-wrap items-center gap-2">
        <Link
          to={`${detailPath}/${application.job_id}`}
          className={cn(
            buttonVariants({ variant: 'outline', size: 'sm' }),
            'flex-1',
          )}
        >
          Xem việc làm
          <ExternalLink className="ml-1.5 h-3.5 w-3.5" aria-hidden="true" />
        </Link>
        {canWithdraw ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={handleWithdraw}
            isLoading={withdrawing}
            disabled={withdrawing}
          >
            <Undo2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            Rút đơn
          </Button>
        ) : null}
      </CardFooter>
    </Card>
  )
}