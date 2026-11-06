import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import type { MembershipRole } from '@/types/workspace'

interface WorkspaceRoleGuardProps {
  allowedRoles: MembershipRole[]
  children?: ReactNode
}

export function WorkspaceRoleGuard({
  allowedRoles,
  children,
}: WorkspaceRoleGuardProps) {
  const { isAuthenticated, isLoading } = useAuth()
  const { selectedWorkspace, isLoading: isWorkspaceLoading } = useWorkspace()
  const location = useLocation()

  if (isLoading || isWorkspaceLoading) {
    return null
  }

  if (!isAuthenticated) {
    return (
      <Navigate to="/login" state={{ from: location.pathname }} replace />
    )
  }

  const role = selectedWorkspace?.role
  if (!role || !allowedRoles.includes(role)) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
