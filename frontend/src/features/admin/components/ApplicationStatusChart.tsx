import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { cn } from '@/utils/cn'
import { APPLICATION_STATUS_LABELS } from '@/features/recruiter/components/StatusUpdateModal'
import type { ApplicationStatusCounts } from '@/types/admin'

export interface ApplicationStatusChartProps {
  counts: ApplicationStatusCounts
}

interface StatusRow {
  key: keyof ApplicationStatusCounts
  className: string
}

const STATUS_ROWS: StatusRow[] = [
  { key: 'applied', className: 'bg-blue-500' },
  { key: 'under_review', className: 'bg-cyan-500' },
  { key: 'shortlisted', className: 'bg-violet-500' },
  { key: 'interviewing', className: 'bg-amber-500' },
  { key: 'accepted', className: 'bg-emerald-500' },
  { key: 'rejected', className: 'bg-rose-500' },
  { key: 'withdrawn', className: 'bg-gray-400' },
]

export function ApplicationStatusChart({
  counts,
}: ApplicationStatusChartProps) {
  const total = STATUS_ROWS.reduce(
    (sum, row) => sum + (counts[row.key] ?? 0),
    0,
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Trạng thái đơn ứng tuyển</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {total === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Chưa có dữ liệu đơn ứng tuyển.
          </p>
        ) : (
          STATUS_ROWS.map((row) => {
            const value = counts[row.key] ?? 0
            const percent = total > 0 ? Math.round((value / total) * 100) : 0
            return (
              <div key={row.key}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    {APPLICATION_STATUS_LABELS[row.key]}
                  </span>
                  <span className="font-medium">
                    {value} ({percent}%)
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                  <div
                    className={cn('h-full rounded-full', row.className)}
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}