import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AppRouter } from './index'
import { AuthProvider } from '@/contexts/AuthContext'
import * as authApi from '@/api/auth'
import * as jobsApi from '@/api/jobs'
import * as aiApi from '@/api/ai'
import * as applicationsApi from '@/api/applications'
import * as companiesApi from '@/api/companies'
import * as adminApi from '@/api/admin'
import * as endpointsApi from '@/api/endpoints'
import type { User, UserRole } from '@/types/auth'
import type { Job } from '@/types/job'
import type { AdminStats } from '@/types/admin'
import type { HealthStatus } from '@/api/endpoints'
import type { JobMatchRecommendation } from '@/types/ai'

const mockUser: User = {
  id: 'user-1',
  email: 'user@example.com',
  role: 'candidate',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const mockJob: Job = {
  id: 'job-1',
  company_id: 'company-1',
  company_name: null,
  title: 'Backend Engineer',
  description: 'Build robust APIs.',
  status: 'published',
  job_type: 'full_time',
  workplace_type: 'remote',
  location: 'Hanoi',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const mockStats: AdminStats = {
  total_users: 5,
  total_candidates: 2,
  total_recruiters: 2,
  total_admins: 1,
  total_companies: 1,
  total_jobs: 2,
  total_applications: 3,
  applications_by_status: {
    applied: 1,
    under_review: 1,
    shortlisted: 1,
    interviewing: 0,
    accepted: 0,
    rejected: 0,
    withdrawn: 0,
  },
}

const mockHealth: HealthStatus = {
  status: 'healthy',
  service: 'AI Recruitment Platform API',
  version: '0.1.0',
  environment: 'test',
}

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  getCurrentUser: vi.fn(),
  createCandidateProfile: vi.fn(),
  createRecruiterProfile: vi.fn(),
}))

vi.mock('@/api/jobs', () => ({
  getJobs: vi.fn(),
  getJobById: vi.fn(),
  getMyJobById: vi.fn(),
}))

vi.mock('@/api/ai', () => ({
  parseResume: vi.fn(),
  getJobRecommendations: vi.fn(),
  getCandidateRecommendations: vi.fn(),
  matchCandidateWithJob: vi.fn(),
  explainMatch: vi.fn(),
  searchJobs: vi.fn(),
  searchCandidates: vi.fn(),
  sendChatMessage: vi.fn(),
  generateInterviewQuestions: vi.fn(),
}))

vi.mock('@/api/applications', () => ({
  applyJob: vi.fn(),
  withdrawApplication: vi.fn(),
  getApplicationsByJob: vi.fn(),
  getMyApplications: vi.fn(),
  getMyApplicationForJob: vi.fn(),
}))

vi.mock('@/api/companies', () => ({
  createCompany: vi.fn(),
  getCompanyById: vi.fn(),
}))

vi.mock('@/api/admin', () => ({
  getAdminStats: vi.fn(),
  getSystemHealth: vi.fn(),
  getAdminUsers: vi.fn(),
  getAdminUserById: vi.fn(),
  deactivateAdminUser: vi.fn(),
  getAdminCompanies: vi.fn(),
  deleteAdminCompany: vi.fn(),
}))

vi.mock('@/api/endpoints', () => {
  return {
    __esModule: true,
    default: {
      health: {
        get: vi.fn(),
      },
    },
  }
})

vi.mock('@/api/metrics', () => ({
  getRecruiterMetrics: vi.fn(),
}))

vi.mock('@/api/notifications', () => ({
  getUnreadNotificationCount: vi.fn().mockResolvedValue({ count: 0 }),
}))

const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)
const mockedGetJobs = vi.mocked(jobsApi.getJobs)
const mockedGetJobById = vi.mocked(jobsApi.getJobById)
const mockedGetMyJobById = vi.mocked(jobsApi.getMyJobById)
const mockedSearchJobs = vi.mocked(aiApi.searchJobs)
const mockedSearchCandidates = vi.mocked(aiApi.searchCandidates)
const mockedGetJobRecommendations = vi.mocked(aiApi.getJobRecommendations)
const mockedGetCandidateRecommendations = vi.mocked(
  aiApi.getCandidateRecommendations,
)
const mockedSendChatMessage = vi.mocked(aiApi.sendChatMessage)
const mockedGenerateInterviewQuestions = vi.mocked(
  aiApi.generateInterviewQuestions,
)
const mockedGetAdminStats = vi.mocked(adminApi.getAdminStats)
const mockedGetSystemHealth = vi.mocked(adminApi.getSystemHealth)
const mockedGetAdminUsers = vi.mocked(adminApi.getAdminUsers)
const mockedGetAdminCompanies = vi.mocked(adminApi.getAdminCompanies)
const mockedGetApplicationsByJob = vi.mocked(
  applicationsApi.getApplicationsByJob,
)
const mockedGetMyApplications = vi.mocked(
  applicationsApi.getMyApplications,
)
const mockedGetMyApplicationForJob = vi.mocked(
  applicationsApi.getMyApplicationForJob,
)
const mockedGetCompanyById = vi.mocked(companiesApi.getCompanyById)
const healthGet = vi.mocked(endpointsApi.default.health.get)
const mockedGetRecruiterMetrics = vi.mocked(
  (await import('@/api/metrics')).getRecruiterMetrics
)

function setUser(role: UserRole) {
  const user: User = { ...mockUser, role }
  mockedGetCurrentUser.mockResolvedValue(user)
  localStorage.setItem('ai_recruitment_token', 'token-abc')
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  mockedGetJobs.mockResolvedValue([mockJob])
  mockedGetJobById.mockResolvedValue(mockJob)
  mockedGetMyJobById.mockResolvedValue(mockJob)
  mockedSearchJobs.mockResolvedValue([])
  mockedSearchCandidates.mockResolvedValue([])
  mockedGetJobRecommendations.mockResolvedValue({ recommendations: [], hasCV: true })
  mockedGetCandidateRecommendations.mockResolvedValue([])
  mockedSendChatMessage.mockRejectedValue(new Error('no chat'))
  mockedGenerateInterviewQuestions.mockRejectedValue(new Error('no interview'))
  mockedGetAdminStats.mockResolvedValue(mockStats)
  mockedGetSystemHealth.mockResolvedValue(mockHealth)
  mockedGetAdminUsers.mockResolvedValue({
    items: [],
    total: 0,
    skip: 0,
    limit: 10,
  })
  mockedGetAdminCompanies.mockResolvedValue({
    items: [],
    total: 0,
    skip: 0,
    limit: 10,
  })
  mockedGetApplicationsByJob.mockResolvedValue([])
  mockedGetMyApplications.mockResolvedValue([])
  mockedGetMyApplicationForJob.mockResolvedValue(null)
  mockedGetCompanyById.mockResolvedValue({
    id: 'company-1',
    name: 'Acme Corp',
    recruiter_id: 'user-1',
  } as never)
  healthGet.mockResolvedValue(mockHealth)
  mockedGetRecruiterMetrics.mockResolvedValue({
    total_jobs: 0,
    total_applications: 0,
    jobs_by_status: [],
    applications_by_status: [],
  })
})

describe('AppRouter public routes', () => {
  it('renders home page at /', async () => {
    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
  })

  it('renders jobs page at /jobs', async () => {
    renderAt('/jobs')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Việc làm' })).toBeInTheDocument()
    })
  })

  it('renders health page at /health', async () => {
    renderAt('/health')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Kiểm tra sức khỏe hệ thống' }),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Hoạt động tốt')).toBeInTheDocument()
  })
})

describe('AppRouter role guards', () => {
  it('redirects anonymous users to /login for protected routes', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('401'))
    localStorage.removeItem('ai_recruitment_token')

    renderAt('/candidate/profile')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
    })
  })

  it('lets a candidate access candidate portal', async () => {
    setUser('candidate')

    renderAt('/candidate/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Tổng quan ứng viên' }),
      ).toBeInTheDocument()
    })
  })

  it('blocks a candidate from recruiter portal', async () => {
    setUser('candidate')

    renderAt('/recruiter/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Tổng quan tuyển dụng' }),
    ).not.toBeInTheDocument()
  })

  it('lets a recruiter access recruiter portal', async () => {
    setUser('recruiter')

    renderAt('/recruiter/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Tổng quan tuyển dụng' }),
      ).toBeInTheDocument()
    })
  })

  it('blocks a recruiter from candidate portal', async () => {
    setUser('recruiter')

    renderAt('/candidate/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Tổng quan ứng viên' }),
    ).not.toBeInTheDocument()
  })

  it('lets an admin access admin dashboard', async () => {
    setUser('admin')

    renderAt('/admin/dashboard')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Tổng quan hệ thống', level: 1 }),
      ).toBeInTheDocument()
    })
  })

  it('blocks an admin-only route for a recruiter', async () => {
    setUser('recruiter')

    renderAt('/admin/dashboard')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Tổng quan hệ thống' }),
    ).not.toBeInTheDocument()
  })

  it('redirects anonymous users from /admin/users to login', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('401'))
    localStorage.removeItem('ai_recruitment_token')

    renderAt('/admin/users')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
    })
  })

  it('blocks a candidate from /admin/users', async () => {
    setUser('candidate')

    renderAt('/admin/users')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Quản lý người dùng' }),
    ).not.toBeInTheDocument()
  })

  it('blocks a recruiter from /admin/users', async () => {
    setUser('recruiter')

    renderAt('/admin/users')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Quản lý người dùng' }),
    ).not.toBeInTheDocument()
  })

  it('lets an admin open the user management page', async () => {
    setUser('admin')

    renderAt('/admin/users')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Quản lý người dùng', level: 1 }),
      ).toBeInTheDocument()
    })
  })

  it('redirects anonymous users from /admin/companies to login', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('401'))
    localStorage.removeItem('ai_recruitment_token')

    renderAt('/admin/companies')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
    })
  })

  it('blocks a candidate from /admin/companies', async () => {
    setUser('candidate')

    renderAt('/admin/companies')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Quản lý công ty' }),
    ).not.toBeInTheDocument()
  })

  it('blocks a recruiter from /admin/companies', async () => {
    setUser('recruiter')

    renderAt('/admin/companies')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Quản lý công ty' }),
    ).not.toBeInTheDocument()
  })

  it('lets an admin open the company management page', async () => {
    setUser('admin')

    renderAt('/admin/companies')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Quản lý công ty', level: 1 }),
      ).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(mockedGetAdminCompanies).toHaveBeenCalled()
    })
  })
})

describe('AppRouter recruiter job routes', () => {
  it('renders interview generator for a recruiter', async () => {
    setUser('recruiter')

    renderAt('/recruiter/jobs/job-1/interview')

    await waitFor(() => {
      expect(screen.getByText('Số câu hỏi')).toBeInTheDocument()
    })
    expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
  })

  it('renders job recommendations for a recruiter', async () => {
    setUser('recruiter')

    renderAt('/recruiter/jobs/job-1/recommendations')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Ứng viên phù hợp cho vị trí' }),
      ).toBeInTheDocument()
    })
    expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
    expect(mockedGetCandidateRecommendations).toHaveBeenCalledWith(
      'job-1',
      10,
    )
  })

  it('renders the job edit page for a recruiter', async () => {
    setUser('recruiter')

    renderAt('/recruiter/jobs/job-1/edit')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Sửa tin tuyển dụng' }),
      ).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(mockedGetMyJobById).toHaveBeenCalledWith('job-1')
    })
  })

  it('blocks a candidate from the recruiter job edit page', async () => {
    setUser('candidate')

    renderAt('/recruiter/jobs/job-1/edit')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Sửa tin tuyển dụng' }),
    ).not.toBeInTheDocument()
  })
})

describe('AppRouter AI routes', () => {
  it('lets a candidate open the AI chat page', async () => {
    setUser('candidate')

    renderAt('/ai/chat')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Trợ lý AI tuyển dụng' }),
      ).toBeInTheDocument()
    })
  })

  it('lets a candidate use semantic job search', async () => {
    setUser('candidate')

    renderAt('/jobs/search')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Tìm kiếm việc làm ngữ nghĩa' }),
      ).toBeInTheDocument()
    })
  })

  it('blocks a candidate from semantic candidate search', async () => {
    setUser('candidate')

    renderAt('/recruiter/search/candidates')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
  })
})

describe('AppRouter Navbar integration', () => {
  it('shows candidate role navigation in the public navbar', async () => {
    setUser('candidate')

    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng chính' }),
      ).toBeInTheDocument()
    })
    const publicNav = screen.getByRole('navigation', {
      name: 'Điều hướng chính',
    })
    expect(within(publicNav).getByText('Trang chủ')).toBeInTheDocument()
    expect(within(publicNav).getByText('Việc làm')).toBeInTheDocument()
    expect(within(publicNav).getByText('Tìm việc AI')).toBeInTheDocument()
    expect(within(publicNav).getByText('Gợi ý việc làm')).toBeInTheDocument()
    expect(within(publicNav).getByText('Trợ lý AI')).toBeInTheDocument()
    // Dashboard link for candidate is "Tổng quan" pointing to /candidate/portal
    const dashboardCta = within(publicNav).getByRole('link', {
      name: 'Tổng quan',
    })
    expect(dashboardCta).toHaveAttribute('href', '/candidate/portal')
  })

  it('shows recruiter role navigation in the public navbar', async () => {
    setUser('recruiter')

    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng chính' }),
      ).toBeInTheDocument()
    })
    const publicNav = screen.getByRole('navigation', {
      name: 'Điều hướng chính',
    })
    expect(within(publicNav).getByText('Trang chủ')).toBeInTheDocument()
    expect(within(publicNav).getByText('Việc làm')).toBeInTheDocument()
    expect(within(publicNav).getByText('Quản lý tuyển dụng')).toBeInTheDocument()
    expect(within(publicNav).getByText('Đăng tin')).toBeInTheDocument()
    expect(within(publicNav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
    expect(within(publicNav).getByText('Trợ lý AI')).toBeInTheDocument()
    // Dashboard link for recruiter is "Quản lý tuyển dụng" pointing to /recruiter/portal
    const dashboardCta = within(publicNav).getByRole('link', {
      name: 'Quản lý tuyển dụng',
    })
    expect(dashboardCta).toHaveAttribute('href', '/recruiter/portal')
  })

  it('shows admin role navigation in the public navbar', async () => {
    setUser('admin')

    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng chính' }),
      ).toBeInTheDocument()
    })
    const publicNav = screen.getByRole('navigation', {
      name: 'Điều hướng chính',
    })
    expect(within(publicNav).getByText('Trang chủ')).toBeInTheDocument()
    expect(within(publicNav).getByText('Việc làm')).toBeInTheDocument()
    expect(within(publicNav).getByText('Bảng điều khiển')).toBeInTheDocument()
    expect(within(publicNav).getByText('Quản lý tuyển dụng')).toBeInTheDocument()
    expect(within(publicNav).getByText('Tìm ứng viên AI')).toBeInTheDocument()
    expect(within(publicNav).getByText('Trợ lý AI')).toBeInTheDocument()
    // Dashboard link for admin is "Bảng điều khiển" pointing to /admin/dashboard
    const dashboardCta = within(publicNav).getByRole('link', {
      name: 'Bảng điều khiển',
    })
    expect(dashboardCta).toHaveAttribute('href', '/admin/dashboard')
  })
})

describe('AppRouter layout integration', () => {
  it('renders the public MainLayout (top navbar) on public routes', async () => {
    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng chính' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('navigation', { name: 'Điều hướng ứng dụng' }),
    ).not.toBeInTheDocument()
  })

  it('renders the private AppShell (sidebar) on /candidate/portal', async () => {
    setUser('candidate')

    renderAt('/candidate/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('navigation', { name: 'Điều hướng chính' }),
    ).not.toBeInTheDocument()
  })

  it('renders the private AppShell (sidebar) on /jobs/search', async () => {
    setUser('candidate')

    renderAt('/jobs/search')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
      ).toBeInTheDocument()
    })
  })

  it('renders the private AppShell (sidebar) on /candidate/recommendations', async () => {
    setUser('candidate')

    renderAt('/candidate/recommendations')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
      ).toBeInTheDocument()
    })
  })

  it('renders the private AppShell (sidebar) on /ai/chat', async () => {
    setUser('candidate')

    renderAt('/ai/chat')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
      ).toBeInTheDocument()
    })
  })

  it('renders the public MainLayout (top navbar) on /jobs/:id', async () => {
    renderAt('/jobs/job-1')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Backend Engineer' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.getByRole('navigation', { name: 'Điều hướng chính' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('navigation', { name: 'Điều hướng ứng dụng' }),
    ).not.toBeInTheDocument()
  })

  it('renders the private AppShell (sidebar) on /candidate/jobs', async () => {
    setUser('candidate')

    renderAt('/candidate/jobs')

    await waitFor(() => {
      expect(
        screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('navigation', { name: 'Điều hướng chính' }),
    ).not.toBeInTheDocument()
  })

  it('renders the private AppShell (sidebar) on /candidate/jobs/:id', async () => {
    setUser('candidate')

    renderAt('/candidate/jobs/job-1')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Backend Engineer' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('navigation', { name: 'Điều hướng chính' }),
    ).not.toBeInTheDocument()
  })

  it('opens /candidate/jobs/:id from a recommendation card inside AppShell', async () => {
    setUser('candidate')
    const recommendation: JobMatchRecommendation = {
      job_id: 'job-1',
      parsed_job: {
        title: 'Recommended Role',
        summary: 'Recommended by AI.',
        required_skills: ['Python'],
        preferred_skills: [],
        minimum_years_experience: 2,
        education_level: null,
      },
      match_result: {
        overall_score: 85,
        cosine_similarity: 0.9,
        skill_coverage_score: 0.85,
        experience_match_score: 0.8,
        matching_skills: ['Python'],
        skill_gap: ['Docker'],
        match_reasons: ['Good fit'],
      },
    }
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: [recommendation], hasCV: true })

    renderAt('/candidate/recommendations')

    await waitFor(() => {
      expect(screen.getByText('Recommended Role')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('link', { name: /Xem chi tiết & Nộp đơn/i }),
    )

    await waitFor(
      () => {
        expect(
          screen.getByRole('heading', { name: 'Backend Engineer' }),
        ).toBeInTheDocument()
      },
      { timeout: 3000 },
    )
    expect(
      screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('navigation', { name: 'Điều hướng chính' }),
    ).not.toBeInTheDocument()
  })
})

describe('AppRouter candidate private jobs', () => {
  it('redirects anonymous users from /candidate/jobs to login', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('401'))
    localStorage.removeItem('ai_recruitment_token')

    renderAt('/candidate/jobs')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Đăng nhập' }),
      ).toBeInTheDocument()
    })
  })

  it('blocks a recruiter from /candidate/jobs', async () => {
    setUser('recruiter')

    renderAt('/candidate/jobs')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Việc làm' }),
    ).not.toBeInTheDocument()
  })

  it('lets a candidate browse jobs at /candidate/jobs', async () => {
    setUser('candidate')

    renderAt('/candidate/jobs')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Việc làm' }),
      ).toBeInTheDocument()
    })
  })

  it('navigates a candidate from /candidate/jobs to /candidate/jobs/:id', async () => {
    setUser('candidate')

    renderAt('/candidate/jobs')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Việc làm' }),
      ).toBeInTheDocument()
    })

    const detailLink = await waitFor(() =>
      screen.getByRole('link', { name: /Xem chi tiết/i }),
    )
    fireEvent.click(detailLink)

    await waitFor(
      () => {
        expect(
          screen.getByRole('heading', { name: 'Backend Engineer' }),
        ).toBeInTheDocument()
      },
      { timeout: 3000 },
    )
    expect(
      screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('navigation', { name: 'Điều hướng chính' }),
    ).not.toBeInTheDocument()
  })
})

describe('AppRouter candidate applications', () => {
  it('redirects anonymous users from /candidate/applications to login', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('401'))
    localStorage.removeItem('ai_recruitment_token')

    renderAt('/candidate/applications')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Đăng nhập' }),
      ).toBeInTheDocument()
    })
  })

  it('blocks a recruiter from /candidate/applications', async () => {
    setUser('recruiter')

    renderAt('/candidate/applications')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Tìm đúng công việc/ }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Đơn ứng tuyển của tôi' }),
    ).not.toBeInTheDocument()
  })

  it('renders the candidate applications page inside AppShell', async () => {
    setUser('candidate')
    mockedGetMyApplications.mockResolvedValue([])

    renderAt('/candidate/applications')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Đơn ứng tuyển của tôi' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.getByRole('navigation', { name: 'Điều hướng ứng dụng' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('navigation', { name: 'Điều hướng chính' }),
    ).not.toBeInTheDocument()
  })
})
