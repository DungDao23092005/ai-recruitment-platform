import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Building2 } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { getMyInvitations } from '@/api/workspaces'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { Spinner } from '@/components/ui/spinner'
import type { MembershipRole } from '@/types/workspace'

interface WorkspaceRoleGuardProps {
  allowedRoles: MembershipRole[]
  children?: ReactNode
  showRecruiterWorkspaceOnboarding?: boolean
}

export function WorkspaceRoleGuard({
  allowedRoles,
  children,
  showRecruiterWorkspaceOnboarding = false,
}: WorkspaceRoleGuardProps) {
  const { currentUser, isAuthenticated, isLoading } = useAuth()
  const { selectedWorkspace, isLoading: isWorkspaceLoading } = useWorkspace()
  const location = useLocation()
  const navigate = useNavigate()

  const [invitationsLoading, setInvitationsLoading] = useState(true)
  const [hasPendingInvitations, setHasPendingInvitations] = useState(false)

  const isRecruiterNoWorkspace =
    Boolean(showRecruiterWorkspaceOnboarding) &&
    currentUser?.role === 'recruiter' &&
    !selectedWorkspace

  useEffect(() => {
    let isMounted = true

    if (
      !isLoading &&
      !isWorkspaceLoading &&
      isAuthenticated &&
      isRecruiterNoWorkspace
    ) {
      setInvitationsLoading(true)
      getMyInvitations()
        .then((invitations) => {
          if (!isMounted) return
          const pending = (invitations || []).some(
            (inv) => inv.status === 'pending' || inv.can_accept,
          )
          setHasPendingInvitations(pending)
          setInvitationsLoading(false)
        })
        .catch(() => {
          if (!isMounted) return
          setHasPendingInvitations(false)
          setInvitationsLoading(false)
        })
    }

    return () => {
      isMounted = false
    }
  }, [
    isLoading,
    isWorkspaceLoading,
    isAuthenticated,
    isRecruiterNoWorkspace,
  ])

  if (isLoading || isWorkspaceLoading) {
    return null
  }

  if (!isAuthenticated) {
    return (
      <Navigate to="/login" state={{ from: location.pathname }} replace />
    )
  }

  if (isRecruiterNoWorkspace) {
    if (invitationsLoading) {
      return (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )
    }

    return (
      <EmptyState
        icon={<Building2 className="h-6 w-6" aria-hidden="true" />}
        title="Chưa có công ty làm việc"
        description={
          hasPendingInvitations
            ? 'Lịch phỏng vấn chỉ hiển thị khi bạn tham gia hoặc tạo một công ty. Bạn có lời mời tham gia công ty đang chờ phản hồi.'
            : 'Lịch phỏng vấn chỉ hiển thị khi bạn tham gia hoặc tạo một công ty.'
        }
      >
        {hasPendingInvitations ? (
          <>
            <Button onClick={() => navigate('/invitations/accept')}>
              Xem lời mời tham gia công ty
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate('/recruiter/company')}
            >
              Tạo công ty
            </Button>
          </>
        ) : (
          <Button onClick={() => navigate('/recruiter/company')}>
            Tạo công ty
          </Button>
        )}
      </EmptyState>
    )
  }

  const role = selectedWorkspace?.role
  if (!role || !allowedRoles.includes(role)) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
