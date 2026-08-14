import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { getAdminStats, getSystemHealth } from '@/api/admin'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { StatsOverviewCard } from '@/features/admin/components/StatsOverviewCard'
import { ApplicationStatusChart } from '@/features/admin/components/ApplicationStatusChart'
import { SystemHealthCard } from '@/features/admin/components/SystemHealthCard'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { AdminStats } from '@/types/admin'
import type { HealthStatus } from '@/api/endpoints'

type StatsState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; stats: AdminStats }

type HealthState =
  | { kind: 'loading' }
  | { kind: 'healthy'; health: HealthStatus }
  | { kind: 'unhealthy'; error: string }

export function AdminDashboardPage() {
  const [statsState, setStatsState] = useState<StatsState>({
    kind: 'loading',
  })
  const [healthState, setHealthState] = useState<HealthState>({
    kind: 'loading',
  })

  const loadStats = useCallback(() => {
    setStatsState({ kind: 'loading' })

    getAdminStats()
      .then((stats) => setStatsState({ kind: 'success', stats }))
      .catch((err) =>
        setStatsState({
          kind: 'error',
          message: getFriendlyErrorMessage(err),
        }),
      )
  }, [])

  const loadHealth = useCallback(() => {
    setHealthState({ kind: 'loading' })

    getSystemHealth()
      .then((health) => setHealthState({ kind: 'healthy', health }))
      .catch((err) =>
        setHealthState({
          kind: 'unhealthy',
          error: getFriendlyErrorMessage(err),
        }),
      )
  }, [])

  useEffect(() => {
    loadStats()
    loadHealth()
  }, [loadStats, loadHealth])

  return (
    <div className="container py-10">
      <PageHeader
        title="Admin Dashboard"
        description="Tổng quan hoạt động và tình trạng hệ thống."
      />

      <div className="mb-6">
        <SystemHealthCard
          status={healthState.kind}
          health={
            healthState.kind === 'healthy' ? healthState.health : null
          }
          error={healthState.kind === 'unhealthy' ? healthState.error : null}
          onRefresh={loadHealth}
        />
      </div>

      {statsState.kind === 'loading' ? (
        <div className="flex min-h-[30vh] items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : null}

      {statsState.kind === 'error' ? (
        <div className="flex min-h-[30vh] flex-col items-center justify-center gap-4 text-center">
          <p className="max-w-md text-sm text-muted-foreground">
            {statsState.message}
          </p>
          <Button variant="outline" onClick={loadStats}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Thử lại
          </Button>
        </div>
      ) : null}

      {statsState.kind === 'success' ? (
        <div className="space-y-6">
          <StatsOverviewCard stats={statsState.stats} />
          <ApplicationStatusChart
            counts={statsState.stats.applications_by_status}
          />
        </div>
      ) : null}
    </div>
  )
}