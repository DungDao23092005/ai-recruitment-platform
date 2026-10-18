import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { Spinner } from '@/components/ui/spinner'
import { hasPendingLockNotice } from '@/utils/lockNotice'

export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!isAuthenticated) {
    // A lock-triggered logout sends the user to the public homepage, where the
    // one-time notice is shown. Every other unauthenticated visit goes to login.
    if (hasPendingLockNotice()) {
      return <Navigate to="/" replace />
    }
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <Outlet />
}