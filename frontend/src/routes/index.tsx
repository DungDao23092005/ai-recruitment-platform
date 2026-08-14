import { Routes, Route } from 'react-router-dom'
import { MainLayout } from '@/layouts/MainLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { HomePage } from '@/pages/HomePage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { HealthCheckPage } from '@/pages/HealthCheckPage'
import { LoginPage } from '@/pages/auth/LoginPage'
import { RegisterPage } from '@/pages/auth/RegisterPage'
import { ProfilePage } from '@/pages/profile/ProfilePage'
import { ProtectedRoute } from '@/components/common/ProtectedRoute'
import { RoleGuard } from '@/components/common/RoleGuard'
import type { UserRole } from '@/types/auth'

export interface AppNavLink {
  to: string
  label: string
}

export const NAV_LINKS: AppNavLink[] = [
  { to: '/', label: 'Home' },
  { to: '/health', label: 'Health' },
]

function ProtectedByRole({
  allowedRoles,
}: {
  allowedRoles: UserRole[]
}) {
  return (
    <RoleGuard allowedRoles={allowedRoles}>
      <ProfilePage />
    </RoleGuard>
  )
}

function AdminPlaceholder() {
  return (
    <div className="container py-10">
      <h1 className="text-2xl font-semibold tracking-tight">
        Admin Overview
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Admin dashboard is coming soon.
      </p>
    </div>
  )
}

export function AppRouter() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/health" element={<HealthCheckPage />} />

        <Route element={<ProtectedRoute />}>
          <Route
            path="/candidate/profile"
            element={<ProtectedByRole allowedRoles={['candidate']} />}
          />
          <Route
            path="/recruiter/profile"
            element={<ProtectedByRole allowedRoles={['recruiter']} />}
          />
          <Route
            path="/admin/overview"
            element={
              <RoleGuard allowedRoles={['admin']}>
                <AdminPlaceholder />
              </RoleGuard>
            }
          />
        </Route>
      </Route>

      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}