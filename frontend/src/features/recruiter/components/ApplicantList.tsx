import { useState } from 'react'
import { CalendarDays, Eye, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { StatusUpdateModal } from './StatusUpdateModal'
import { ApplicationDetailModal } from './ApplicationDetailModal'
import { ApplicationStatusBadge } from '@/components/common/ApplicationStatusBadge'
import type { Application } from '@/types/application'

function getCandidateDisplayName(application: Application): string {
  const fullName = application.candidate?.full_name
  if (fullName) {
    return fullName
  }
  return `Ứng viên ${application.candidate_id.slice(0, 8)}`
}

function getCandidateTitle(application: Application): string {
  return application.candidate?.title ?? 'Hồ sơ ứng viên'
}

export interface ApplicantListProps {
  applications: Application[]
  onStatusChange?: (updated: Application) => void
}

function formatSubmitted(dateString: string): string {
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

export function ApplicantList({
  applications,
  onStatusChange,
}: ApplicantListProps) {
  const [selected, setSelected] = useState<Application | null>(null)
  const [detail, setDetail] = useState<Application | null>(null)

  if (applications.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed bg-muted/30 px-6 py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-background text-muted-foreground shadow-sm">
          <User className="h-5 w-5" aria-hidden="true" />
        </div>
        <p className="font-display text-base font-semibold text-foreground">
          Chưa có ứng viên
        </p>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">
          Tin tuyển dụng này chưa nhận được đơn ứng tuyển nào.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {applications.map((application) => (
        <Card key={application.id} className="transition-shadow hover:shadow-soft">
          <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <User className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <p className="truncate font-medium">
                  {getCandidateDisplayName(application)}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {getCandidateTitle(application)}
                </p>
                <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                  <CalendarDays className="h-3 w-3" aria-hidden="true" />
                  {formatSubmitted(application.created_at) ||
                    'Không có ngày nộp đơn'}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <ApplicationStatusBadge status={application.status} />
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDetail(application)}
                aria-label={`Xem hồ sơ ứng viên ${application.candidate_id.slice(0, 8)}`}
              >
                <Eye className="h-4 w-4" aria-hidden="true" />
                Xem hồ sơ
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelected(application)}
                aria-label={`Cập nhật trạng thái cho đơn ứng tuyển ${application.id.slice(0, 8)}`}
              >
                Cập nhật trạng thái
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}

      {selected ? (
        <StatusUpdateModal
          application={selected}
          onClose={() => setSelected(null)}
          onSuccess={(updated) => {
            setSelected(null)
            onStatusChange?.(updated)
          }}
        />
      ) : null}

      {detail ? (
        <ApplicationDetailModal
          application={detail}
          onClose={() => setDetail(null)}
          onStatusChange={(updated) => {
            onStatusChange?.(updated)
          }}
        />
      ) : null}
    </div>
  )
}