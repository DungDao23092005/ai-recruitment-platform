import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import endpoints, { type HealthStatus } from '@/api/endpoints'
import { Spinner } from '@/components/ui/spinner'
import { Badge } from '@/components/ui/badge'

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
          error instanceof Error ? error.message : 'Unknown error'
        setState({ kind: 'error', message })
      })

    return () => {
      active = false
    }
  }, [])

  return (
    <div className="container py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Health Check</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Verifying connectivity to the backend API.
      </p>

      <div className="mt-6 max-w-xl space-y-3">
        {state.kind === 'loading' ? (
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Spinner size="sm" />
            <span>Checking backend...</span>
          </div>
        ) : null}

        {state.kind === 'success' ? (
          <>
            <div className="flex items-center gap-2">
              <Badge variant="success">Healthy</Badge>
              <span className="text-sm text-muted-foreground">
                {state.data.service ?? 'Backend API'}
              </span>
            </div>
            <dl className="rounded-lg border bg-muted/30 p-4 text-sm">
              <div className="flex justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Status</dt>
                <dd className="font-medium">{state.data.status}</dd>
              </div>
              <div className="flex justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Version</dt>
                <dd className="font-medium">{state.data.version ?? 'N/A'}</dd>
              </div>
              <div className="flex justify-between gap-4 py-1">
                <dt className="text-muted-foreground">Environment</dt>
                <dd className="font-medium">
                  {state.data.environment ?? 'N/A'}
                </dd>
              </div>
            </dl>
          </>
        ) : null}

        {state.kind === 'error' ? (
          <div className="flex items-center gap-2">
            <Badge variant="destructive">Unreachable</Badge>
            <span className="text-sm text-muted-foreground">
              {state.message}. Is the backend running?
            </span>
          </div>
        ) : null}

        <p className="text-sm text-muted-foreground">
          <Link to="/" className="text-primary underline underline-offset-4">
            Back to home
          </Link>
        </p>
      </div>
    </div>
  )
}