import { Routes, Route } from 'react-router-dom'
import { MainLayout } from '@/layouts/MainLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { DashboardLayout } from '@/layouts/DashboardLayout'
import { HomePage } from '@/pages/HomePage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { HealthCheckPage } from '@/pages/HealthCheckPage'
import { LoginPage } from '@/pages/auth/LoginPage'
import { RegisterPage } from '@/pages/auth/RegisterPage'
import { ProfilePage } from '@/pages/profile/ProfilePage'
import { JobsPage } from '@/pages/jobs/JobsPage'
import { JobDetailPage } from '@/pages/jobs/JobDetailPage'
import { SemanticJobSearchPage } from '@/pages/jobs/SemanticJobSearchPage'
import { ResumeUploadPage } from '@/features/candidate/pages/ResumeUploadPage'
import { CandidatePortalPage } from '@/features/candidate/pages/CandidatePortalPage'
import { CandidateRecommendationsPage } from '@/pages/candidate/CandidateRecommendationsPage'
import { AdminDashboardPage } from '@/features/admin/pages/AdminDashboardPage'
import { RecruiterPortalPage } from '@/features/recruiter/pages/RecruiterPortalPage'
import { RecruiterCompanyPage } from '@/features/recruiter/pages/RecruiterCompanyPage'
import { RecruiterJobsPage } from '@/features/recruiter/pages/RecruiterJobsPage'
import { JobCreatePage } from '@/features/recruiter/pages/JobCreatePage'
import { JobApplicantsPage } from '@/features/recruiter/pages/JobApplicantsPage'
import { JobRecommendationsPage } from '@/features/recruiter/pages/JobRecommendationsPage'
import { SemanticCandidateSearchPage } from '@/features/recruiter/pages/SemanticCandidateSearchPage'
import { ProtectedRoute } from '@/components/common/ProtectedRoute'
import { RoleGuard } from '@/components/common/RoleGuard'
import type { UserRole } from '@/types/auth'

export interface AppNavLink {
  to: string
  label: string
}

export const NAV_LINKS: AppNavLink[] = [
  { to: '/', label: 'Home' },
  { to: '/jobs', label: 'Việc làm' },
  { to: '/health', label: 'Health' },
]

function ProtectedByRole({
  allowedRoles,
  children,
}: {
  allowedRoles: UserRole[]
  children: React.ReactNode
}) {
  return <RoleGuard allowedRoles={allowedRoles}>{children}</RoleGuard>
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
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:id" element={<JobDetailPage />} />

        <Route element={<ProtectedRoute />}>
          <Route
            path="/jobs/search"
            element={
              <ProtectedByRole allowedRoles={['candidate', 'recruiter', 'admin']}>
                <SemanticJobSearchPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/candidate/profile"
            element={
              <ProtectedByRole allowedRoles={['candidate']}>
                <ProfilePage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/candidate/cv-upload"
            element={
              <ProtectedByRole allowedRoles={['candidate']}>
                <ResumeUploadPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/candidate/portal"
            element={
              <ProtectedByRole allowedRoles={['candidate']}>
                <CandidatePortalPage />
              </ProtectedByRole>
            }
          />
          <Route element={<DashboardLayout />}>
            <Route
              path="/candidate/recommendations"
              element={
                <ProtectedByRole allowedRoles={['candidate']}>
                  <CandidateRecommendationsPage />
                </ProtectedByRole>
              }
            />
          </Route>
          <Route
            path="/recruiter/profile"
            element={
              <ProtectedByRole allowedRoles={['recruiter']}>
                <ProfilePage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/recruiter/portal"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <RecruiterPortalPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/recruiter/company"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <RecruiterCompanyPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/recruiter/jobs"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <RecruiterJobsPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/recruiter/jobs/new"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <JobCreatePage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/recruiter/jobs/:id/applicants"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <JobApplicantsPage />
              </ProtectedByRole>
            }
          />
          <Route element={<DashboardLayout />}>
            <Route
              path="/recruiter/jobs/:id/recommendations"
              element={
                <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                  <JobRecommendationsPage />
                </ProtectedByRole>
              }
            />
          </Route>
          <Route element={<DashboardLayout />}>
            <Route
              path="/recruiter/search/candidates"
              element={
                <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                  <SemanticCandidateSearchPage />
                </ProtectedByRole>
              }
            />
          </Route>
          <Route
            path="/admin/dashboard"
            element={
              <RoleGuard allowedRoles={['admin']}>
                <AdminDashboardPage />
              </RoleGuard>
            }
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