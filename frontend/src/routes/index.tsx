import { Routes, Route } from 'react-router-dom'
import { MainLayout } from '@/layouts/MainLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { AppShell } from '@/layouts/AppShell'
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
import { CandidateApplicationsPage } from '@/features/candidate/pages/CandidateApplicationsPage'
import { CandidateRecommendationsPage } from '@/pages/candidate/CandidateRecommendationsPage'
import { AdminDashboardPage } from '@/features/admin/pages/AdminDashboardPage'
import { AdminUsersPage } from '@/features/admin/pages/AdminUsersPage'
import { RecruiterPortalPage } from '@/features/recruiter/pages/RecruiterPortalPage'
import { RecruiterCompanyPage } from '@/features/recruiter/pages/RecruiterCompanyPage'
import { RecruiterJobsPage } from '@/features/recruiter/pages/RecruiterJobsPage'
import { JobCreatePage } from '@/features/recruiter/pages/JobCreatePage'
import { RecruiterJobEditPage } from '@/features/recruiter/pages/RecruiterJobEditPage'
import { JobApplicantsPage } from '@/features/recruiter/pages/JobApplicantsPage'
import { JobRecommendationsPage } from '@/features/recruiter/pages/JobRecommendationsPage'
import { InterviewGeneratorPage } from '@/features/recruiter/pages/InterviewGeneratorPage'
import { SemanticCandidateSearchPage } from '@/features/recruiter/pages/SemanticCandidateSearchPage'
import { AIChatPage } from '@/pages/ai/AIChatPage'
import { ProtectedRoute } from '@/components/common/ProtectedRoute'
import { RoleGuard } from '@/components/common/RoleGuard'
import type { UserRole } from '@/types/auth'

export interface AppNavLink {
  to: string
  label: string
}

export const NAV_LINKS: AppNavLink[] = [
  { to: '/', label: 'Trang chủ' },
  { to: '/jobs', label: 'Việc làm' },
  { to: '/health', label: 'Sức khỏe hệ thống' },
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

export function AppRouter() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/health" element={<HealthCheckPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:id" element={<JobDetailPage />} />
      </Route>

      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route
            path="/jobs/search"
            element={
              <ProtectedByRole allowedRoles={['candidate', 'recruiter', 'admin']}>
                <SemanticJobSearchPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/ai/chat"
            element={
              <RoleGuard allowedRoles={['candidate', 'recruiter', 'admin']}>
                <AIChatPage />
              </RoleGuard>
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
          <Route
            path="/candidate/recommendations"
            element={
              <ProtectedByRole allowedRoles={['candidate']}>
                <CandidateRecommendationsPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/candidate/applications"
            element={
              <ProtectedByRole allowedRoles={['candidate']}>
                <CandidateApplicationsPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/candidate/jobs"
            element={
              <ProtectedByRole allowedRoles={['candidate']}>
                <JobsPage detailPath="/candidate/jobs" contained={false} />
              </ProtectedByRole>
            }
          />
          <Route
            path="/candidate/jobs/:id"
            element={
              <ProtectedByRole allowedRoles={['candidate']}>
                <JobDetailPage backPath="/candidate/jobs" />
              </ProtectedByRole>
            }
          />
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
            path="/recruiter/jobs/:id/edit"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <RecruiterJobEditPage />
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
          <Route
            path="/recruiter/jobs/:id/recommendations"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <JobRecommendationsPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/recruiter/jobs/:id/interview"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <InterviewGeneratorPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/recruiter/search/candidates"
            element={
              <ProtectedByRole allowedRoles={['recruiter', 'admin']}>
                <SemanticCandidateSearchPage />
              </ProtectedByRole>
            }
          />
          <Route
            path="/admin/dashboard"
            element={
              <RoleGuard allowedRoles={['admin']}>
                <AdminDashboardPage />
              </RoleGuard>
            }
          />
          <Route
            path="/admin/users"
            element={
              <RoleGuard allowedRoles={['admin']}>
                <AdminUsersPage />
              </RoleGuard>
            }
          />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}