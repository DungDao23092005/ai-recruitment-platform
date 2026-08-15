import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Server } from 'lucide-react'
import endpoints, { type HealthStatus } from '@/api/endpoints'
import { Spinner } from '@/components/ui/spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/common/PageHeader'

type HealthState =
  | { kind: 'loading' }
  | { kind: 'success'; data: HealthStatus }
  | { kind: 'error'; message: string }

export function HealthCheckPage() {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    let active = true

    endpoints.health
      .get()
      .then((data) => {
        if (active) setState({ kind: 'success', data })
      })
      .catch((error: unknown) => {
        if (!active) return
        const message =
          error instanceof Error ? error.message : 'Lỗi không xác định'
        setState({ kind: 'error', message })
      })

    return () => {
      active = false
    }
  }, [])

  return (
    <div className="container py-10 sm:py-12">
      <PageHeader
        eyebrow="Vận hành"
        title="Kiểm tra sức khỏe hệ thống"
        description="Xác minh kết nối tới API backend của nền tảng."
      />

      <div className="mt-6 max-w-xl space-y-4">
        {state.kind === 'loading' ? (
          <div className="flex items-center gap-3 rounded-xl border bg-card p-4 text-sm text-muted-foreground">
            <Spinner size="sm" />
            <span>Đang kiểm tra backend...</span>
          </div>
        ) : null}

        {state.kind === 'success' ? (
          <div className="rounded-xl border bg-card p-5 shadow-soft">
            <div className="flex items-center gap-2">
              <Badge variant="success">Hoạt động tốt</Badge>
              <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Server className="h-4 w-4" aria-hidden="true" />
                {state.data.service ?? 'API Backend'}
              </span>
            </div>
            <dl className="mt-4 space-y-1 border-t pt-4 text-sm">
              <div className="flex items-center justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Trạng thái</dt>
                <dd className="font-medium">{state.data.status}</dd>
              </div>
              <div className="flex items-center justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Phiên bản</dt>
                <dd className="font-medium">
                  {state.data.version ?? 'Chưa có'}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Môi trường</dt>
                <dd className="font-medium">
                  {state.data.environment ?? 'Chưa có'}
                </dd>
              </div>
            </dl>
          </div>
        ) : null}

        {state.kind === 'error' ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
            <div className="flex items-center gap-2">
              <Badge variant="destructive">Không kết nối được</Badge>
              <span className="text-sm text-muted-foreground">
                {state.message}. Backend có đang chạy không?
              </span>
            </div>
          </div>
        ) : null}

        <Link to="/">
          <Button variant="ghost" size="sm" className="text-muted-foreground">
            <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
            Về trang chủ
          </Button>
        </Link>
      </div>
    </div>
  )
}