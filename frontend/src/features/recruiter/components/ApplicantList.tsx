import { useState } from 'react'
import { User, CalendarDays } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { StatusUpdateModal } from './StatusUpdateModal'
import { APPLICATION_STATUS_LABELS } from './StatusUpdateModal'
import type { Application } from '@/types/application'

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

  return (
    <div className="space-y-4">
      {applications.map((application) => (
        <Card key={application.id}>
          <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
                <User className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="font-medium">
                  Ứng viên {application.candidate_id.slice(0, 8)}
                </p>
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <CalendarDays className="h-3 w-3" aria-hidden="true" />
                  {formatSubmitted(application.created_at) ||
                    'Không có ngày nộp đơn'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="neutral">
                {APPLICATION_STATUS_LABELS[application.status]}
              </Badge>
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
    </div>
  )
}