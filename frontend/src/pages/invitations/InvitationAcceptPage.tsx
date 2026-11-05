import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Building2, MailCheck, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { acceptInvitation, previewInvitation } from '@/api/workspaces'
import { useAuth } from '@/contexts/AuthContext'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import {
  MEMBERSHIP_ROLE_LABELS,
  type InvitationPreview,
} from '@/types/workspace'
import { getFriendlyErrorMessage } from '@/utils/errors'

interface InvitationLocationState {
  invitationToken?: string
}

function readTokenFromHash(): string | null {
  const rawHash = window.location.hash.replace(/^#/, '')
  if (!rawHash) return null
  return new URLSearchParams(rawHash).get('token')
}

function clearInvitationFragment(): void {
  if (!window.location.hash) return
  window.history.replaceState(
    window.history.state,
    '',
    `${window.location.pathname}${window.location.search}`,
  )
}

export function InvitationAcceptPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const { refreshWorkspaces, selectWorkspace } = useWorkspace()
  const navigate = useNavigate()
  const location = useLocation()
  const [token] = useState<string | null>(() => {
    const stateToken = (location.state as InvitationLocationState | null)
      ?.invitationToken
    return readTokenFromHash() ?? stateToken ?? null
  })
  const [preview, setPreview] = useState<InvitationPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isAccepting, setIsAccepting] = useState(false)

  useEffect(() => {
    clearInvitationFragment()
    if (!token) {
      setError('Li\u00ean k\u1ebft l\u1eddi m\u1eddi kh\u00f4ng h\u1ee3p l\u1ec7 ho\u1eb7c \u0111\u00e3 b\u1ecb thi\u1ebfu m\u00e3.')
      setIsLoading(false)
    }
  }, [token])

  const loadPreview = useCallback(async (invitationToken: string) => {
    setIsLoading(true)
    setError(null)
    try {
      setPreview(await previewInvitation(invitationToken))
    } catch (previewError) {
      setError(getFriendlyErrorMessage(previewError))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (token) {
      void loadPreview(token)
    }
  }, [loadPreview, token])

  const handleAccept = async () => {
    if (!token) return
    setIsAccepting(true)
    setError(null)
    try {
      const result = await acceptInvitation(token)
      selectWorkspace(result.workspace.company_id)
      await refreshWorkspaces()
      navigate('/recruiter/portal', { replace: true })
    } catch (acceptError) {
      setError(getFriendlyErrorMessage(acceptError))
    } finally {
      setIsAccepting(false)
    }
  }

  return (
    <div className="container flex min-h-[70vh] items-center justify-center py-10">
      <Card className="w-full max-w-lg shadow-soft">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-display text-xl font-bold">
            <MailCheck className="h-5 w-5 text-primary" aria-hidden="true" />
            Lời mời tham gia công ty
          </CardTitle>
          <CardDescription>
            Chấp nhận lời mời để truy cập không gian làm việc của công ty.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {isLoading || authLoading ? (
            <div className="flex justify-center py-8">
              <Spinner size="lg" />
            </div>
          ) : error ? (
            <div
              role="alert"
              className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
            >
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4" aria-hidden="true" />
                <span>{error}</span>
              </div>
            </div>
          ) : preview ? (
            <div className="space-y-4">
              <div className="rounded-lg border bg-muted/30 p-4">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <Building2 className="h-4 w-4 text-primary" aria-hidden="true" />
                  {preview.company_name}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Vai trò: {MEMBERSHIP_ROLE_LABELS[preview.role]}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Email được mời: {preview.email_masked}
                </p>
              </div>

              {!preview.can_accept ? (
                <p className="text-sm text-muted-foreground">
                  Lời mời này không còn hiệu lực.
                </p>
              ) : isAuthenticated ? (
                <Button
                  className="w-full"
                  onClick={() => void handleAccept()}
                  isLoading={isAccepting}
                >
                  Tham gia công ty
                </Button>
              ) : (
                <Button
                  className="w-full"
                  onClick={() => {
                    navigate('/login', {
                      state: {
                        from: location.pathname,
                        invitationToken: token,
                      },
                    })
                  }}
                >
                  Đăng nhập để tham gia
                </Button>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
