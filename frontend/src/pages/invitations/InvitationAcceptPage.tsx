import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Building2, CheckCircle2, MailCheck, ShieldAlert, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Modal } from '@/components/ui/modal'
import { Spinner } from '@/components/ui/spinner'
import {
  acceptInvitation,
  acceptMyInvitation,
  declineInvitation,
  declineMyInvitation,
  getMyInvitations,
  previewInvitation,
} from '@/api/workspaces'
import { useAuth } from '@/contexts/AuthContext'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import {
  MEMBERSHIP_ROLE_LABELS,
  type InvitationPreview,
} from '@/types/workspace'
import { getFriendlyErrorMessage } from '@/utils/errors'

interface InvitationLocationState {
  invitationToken?: string
  invitationAction?: 'accept' | 'decline'
  invitationId?: string
}

function readParamsFromHash(): {
  token: string | null
  action: 'accept' | 'decline' | null
} {
  const rawHash = window.location.hash.replace(/^#/, '')
  if (!rawHash) return { token: null, action: null }
  const params = new URLSearchParams(rawHash)
  const token = params.get('token')
  const actionParam = params.get('action')
  const action =
    actionParam === 'decline'
      ? 'decline'
      : actionParam === 'accept'
        ? 'accept'
        : null
  return { token, action }
}

function clearInvitationFragment(): void {
  if (!window.location.hash) return
  window.history.replaceState(
    window.history.state,
    '',
    `${window.location.pathname}${window.location.search}`,
  )
}

function formatExpiryDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

export function InvitationAcceptPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const { refreshWorkspaces, selectWorkspace } = useWorkspace()
  const navigate = useNavigate()
  const location = useLocation()

  const initialHashRef = useRef(readParamsFromHash())
  const locationState = location.state as InvitationLocationState | null

  const [token] = useState<string | null>(
    () => initialHashRef.current.token ?? locationState?.invitationToken ?? null,
  )
  const [initialAction] = useState<'accept' | 'decline'>(
    () =>
      initialHashRef.current.action ??
      locationState?.invitationAction ??
      'accept',
  )
  const [invitationId, setInvitationId] = useState<string | null>(
    () => locationState?.invitationId ?? null,
  )

  const [preview, setPreview] = useState<InvitationPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isDeclined, setIsDeclined] = useState(false)
  const [confirmAction, setConfirmAction] = useState<'accept' | 'decline' | null>(
    null,
  )

  useEffect(() => {
    clearInvitationFragment()
  }, [])

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      if (token) {
        const data = await previewInvitation(token)
        setPreview(data)
      } else if (isAuthenticated) {
        const myInvites = await getMyInvitations()
        let target = myInvites[0]
        if (invitationId) {
          const match = myInvites.find((inv) => inv.id === invitationId)
          if (match) target = match
        }
        if (target) {
          setInvitationId(target.id)
          setPreview({
            company_name: target.company_name,
            company_slug: target.company_slug,
            email_masked: '',
            role: target.role,
            status: target.status,
            expires_at: target.expires_at,
            can_accept: target.can_accept,
          })
        } else {
          setError('Không tìm thấy lời mời tham gia công ty đang chờ.')
        }
      } else {
        setError('Liên kết lời mời không hợp lệ hoặc đã bị thiếu mã.')
      }
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }, [token, isAuthenticated, invitationId])

  useEffect(() => {
    if (!authLoading) {
      void loadData()
    }
  }, [loadData, authLoading])

  const handleConfirmAction = async () => {
    if (!confirmAction) return
    setIsSubmitting(true)
    setError(null)
    try {
      if (confirmAction === 'accept') {
        if (token) {
          const result = await acceptInvitation(token)
          selectWorkspace(result.workspace.company_id)
          await refreshWorkspaces()
        } else if (invitationId) {
          const result = await acceptMyInvitation(invitationId)
          selectWorkspace(result.workspace.company_id)
          await refreshWorkspaces()
        }
        window.dispatchEvent(new CustomEvent('notification:read'))
        navigate('/recruiter/portal', { replace: true })
      } else {
        if (token) {
          await declineInvitation(token)
        } else if (invitationId) {
          await declineMyInvitation(invitationId)
        }
        window.dispatchEvent(new CustomEvent('notification:read'))
        setIsDeclined(true)
        setConfirmAction(null)
      }
    } catch (actionError) {
      setError(getFriendlyErrorMessage(actionError))
      setConfirmAction(null)
    } finally {
      setIsSubmitting(false)
    }
  }

  const roleLabel = preview ? MEMBERSHIP_ROLE_LABELS[preview.role] : ''

  return (
    <div className="container flex min-h-[70vh] items-center justify-center py-10">
      <Card className="w-full max-w-lg shadow-soft">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-display text-xl font-bold">
            <MailCheck className="h-5 w-5 text-primary" aria-hidden="true" />
            Lời mời tham gia công ty
          </CardTitle>
          <CardDescription>
            Xem lại thông tin và xác nhận tham gia hoặc từ chối lời mời.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {isLoading || authLoading ? (
            <div className="flex justify-center py-8">
              <Spinner size="lg" />
            </div>
          ) : isDeclined ? (
            <div className="space-y-4 text-center py-4">
              <XCircle className="mx-auto h-12 w-12 text-muted-foreground" aria-hidden="true" />
              <h3 className="text-lg font-semibold text-foreground">
                Đã từ chối lời mời
              </h3>
              <p className="text-sm text-muted-foreground">
                Bạn đã từ chối lời mời tham gia công ty{' '}
                <strong>{preview?.company_name}</strong>.
              </p>
              <Button
                variant="outline"
                className="mt-4"
                onClick={() => navigate('/')}
              >
                Về trang chủ
              </Button>
            </div>
          ) : error ? (
            <div
              role="alert"
              className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
            >
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
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
                  Vai trò: <span className="font-medium text-foreground">{roleLabel}</span>
                </p>
                {preview.email_masked ? (
                  <p className="mt-1 text-sm text-muted-foreground">
                    Email được mời: {preview.email_masked}
                  </p>
                ) : null}
                <p className="mt-1 text-xs text-muted-foreground">
                  Hạn phản hồi: {formatExpiryDate(preview.expires_at)}
                </p>
              </div>

              {!preview.can_accept ? (
                <p className="text-sm text-muted-foreground">
                  Lời mời này không còn hiệu lực.
                </p>
              ) : isAuthenticated ? (
                <div className="space-y-2">
                  <div className="flex flex-col sm:flex-row gap-3">
                    <Button
                      className="flex-1"
                      onClick={() => setConfirmAction('accept')}
                      variant={initialAction === 'decline' ? 'outline' : 'default'}
                    >
                      <CheckCircle2 className="mr-2 h-4 w-4" aria-hidden="true" />
                      Chấp nhận lời mời
                    </Button>
                    <Button
                      variant={initialAction === 'decline' ? 'destructive' : 'outline'}
                      className="flex-1"
                      onClick={() => setConfirmAction('decline')}
                    >
                      <XCircle className="mr-2 h-4 w-4" aria-hidden="true" />
                      Từ chối lời mời
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs text-muted-foreground">
                    Vui lòng đăng nhập hoặc tạo tài khoản với email nhận lời mời để phản hồi.
                  </p>
                  <div className="flex flex-col sm:flex-row gap-3">
                    <Button
                      className="flex-1"
                      onClick={() => {
                        navigate('/login', {
                          state: {
                            from: location.pathname,
                            invitationToken: token,
                            invitationAction: initialAction,
                            invitationRole: preview.role,
                          },
                        })
                      }}
                    >
                      Đăng nhập để tham gia
                    </Button>
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() => {
                        navigate('/register', {
                          state: {
                            from: location.pathname,
                            invitationToken: token,
                            invitationAction: initialAction,
                            invitationRole: preview.role,
                          },
                        })
                      }}
                    >
                      Tạo tài khoản mới
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {confirmAction ? (
        <Modal
          onClose={() => setConfirmAction(null)}
          size="sm"
          title={
            confirmAction === 'accept'
              ? 'Xác nhận chấp nhận lời mời'
              : 'Xác nhận từ chối lời mời'
          }
          description={`Công ty: ${preview?.company_name}`}
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => setConfirmAction(null)}
                disabled={isSubmitting}
              >
                Hủy
              </Button>
              <Button
                variant={confirmAction === 'accept' ? 'default' : 'destructive'}
                onClick={() => void handleConfirmAction()}
                isLoading={isSubmitting}
                disabled={isSubmitting}
              >
                {confirmAction === 'accept'
                  ? 'Xác nhận tham gia'
                  : 'Xác nhận từ chối'}
              </Button>
            </>
          }
        >
          <p className="text-sm text-muted-foreground">
            {confirmAction === 'accept'
              ? `Bạn có chắc chắn muốn tham gia ${preview?.company_name} với vai trò ${roleLabel}? Bạn sẽ có quyền truy cập vào không gian làm việc của công ty.`
              : `Bạn có chắc chắn muốn từ chối lời mời tham gia ${preview?.company_name}? Hành động này sẽ từ chối quyền truy cập và không thể hoàn tác.`}
          </p>
        </Modal>
      ) : null}
    </div>
  )
}
