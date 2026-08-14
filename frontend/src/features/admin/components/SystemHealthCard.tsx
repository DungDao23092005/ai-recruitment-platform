import { RefreshCw, Server, CheckCircle2, XCircle } from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import type { HealthStatus } from '@/api/endpoints'

export interface SystemHealthCardProps {
  status: 'loading' | 'healthy' | 'unhealthy'
  health: HealthStatus | null
  error: string | null
  onRefresh: () => void
}

export function SystemHealthCard({
  status,
  health,
  error,
  onRefresh,
}: SystemHealthCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-lg">Tình trạng hệ thống</CardTitle>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          disabled={status === 'loading'}
          aria-label="Refresh system health"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </Button>
      </CardHeader>
      <CardContent>
        {status === 'loading' ? (
          <div className="flex min-h-[120px] flex-col items-center justify-center gap-3">
            <Spinner />
            <p className="text-sm text-muted-foreground">
              Đang kiểm tra backend...
            </p>
          </div>
        ) : null}

        {status === 'healthy' && health ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden="true" />
              <Badge variant="success">Healthy</Badge>
            </div>
            <dl className="rounded-lg border bg-muted/30 p-4 text-sm">
              <div className="flex justify-between gap-4 py-1">
                <dt className="flex items-center gap-1 text-muted-foreground">
                  <Server className="h-4 w-4" aria-hidden="true" />
                  Service
                </dt>
                <dd className="font-medium">{health.service ?? 'Backend API'}</dd>
              </div>
              <div className="flex justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Status</dt>
                <dd className="font-medium">{health.status}</dd>
              </div>
              <div className="flex justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Version</dt>
                <dd className="font-medium">{health.version ?? 'N/A'}</dd>
              </div>
              <div className="flex justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Environment</dt>
                <dd className="font-medium">
                  {health.environment ?? 'N/A'}
                </dd>
              </div>
            </dl>
          </div>
        ) : null}

        {status === 'unhealthy' ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-rose-600" aria-hidden="true" />
              <Badge variant="destructive">Unreachable</Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {error ?? 'Cannot reach the backend API. Is it running?'}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}