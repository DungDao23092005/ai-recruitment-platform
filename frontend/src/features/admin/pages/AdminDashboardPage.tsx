import { useCallback, useEffect, useState } from 'react'
import { getAdminStats, getSystemHealth } from '@/api/admin'
import { PageHeader } from '@/components/common/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
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
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Tổng quan hệ thống"
        description="Thống kê người dùng, công ty, tin tuyển dụng và tình trạng hệ thống."
      />

      <SystemHealthCard
        status={healthState.kind}
        health={healthState.kind === 'healthy' ? healthState.health : null}
        error={healthState.kind === 'unhealthy' ? healthState.error : null}
        onRefresh={loadHealth}
      />

      {statsState.kind === 'loading' ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 7 }).map((_, index) => (
              <Skeleton key={index} className="h-20 w-full" />
            ))}
          </div>
          <Skeleton className="h-64 w-full" />
        </div>
      ) : null}

      {statsState.kind === 'error' ? (
        <ErrorBanner message={statsState.message} onRetry={loadStats} />
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