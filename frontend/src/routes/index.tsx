import { Routes, Route } from 'react-router-dom'
import { MainLayout } from '@/layouts/MainLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { DashboardLayout } from '@/layouts/DashboardLayout'
import { HomePage } from '@/pages/HomePage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { HealthCheckPage } from '@/pages/HealthCheckPage'

export interface AppNavLink {
  to: string
  label: string
}

export const NAV_LINKS: AppNavLink[] = [
  { to: '/', label: 'Home' },
  { to: '/health', label: 'Health' },
]

export function AppRouter() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/health" element={<HealthCheckPage />} />
      </Route>
      <Route path="/auth" element={<AuthLayout />} />
      <Route path="/dashboard" element={<DashboardLayout />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}