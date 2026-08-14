import { render, screen, waitFor } from '@testing-library/react'
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
  getApplicationsByJob: vi.fn(),
}))

vi.mock('@/api/companies', () => ({
  createCompany: vi.fn(),
  getCompanyById: vi.fn(),
}))

vi.mock('@/api/admin', () => ({
  getAdminStats: vi.fn(),
  getSystemHealth: vi.fn(),
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

const mockedGetCurrentUser = vi.mocked(authApi.getCurrentUser)
const mockedGetJobs = vi.mocked(jobsApi.getJobs)
const mockedGetJobById = vi.mocked(jobsApi.getJobById)
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
const mockedGetApplicationsByJob = vi.mocked(
  applicationsApi.getApplicationsByJob,
)
const mockedGetCompanyById = vi.mocked(companiesApi.getCompanyById)
const healthGet = vi.mocked(endpointsApi.default.health.get)

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
  mockedSearchJobs.mockResolvedValue([])
  mockedSearchCandidates.mockResolvedValue([])
  mockedGetJobRecommendations.mockResolvedValue([])
  mockedGetCandidateRecommendations.mockResolvedValue([])
  mockedSendChatMessage.mockRejectedValue(new Error('no chat'))
  mockedGenerateInterviewQuestions.mockRejectedValue(new Error('no interview'))
  mockedGetAdminStats.mockResolvedValue(mockStats)
  mockedGetSystemHealth.mockResolvedValue(mockHealth)
  mockedGetApplicationsByJob.mockResolvedValue([])
  mockedGetCompanyById.mockResolvedValue({
    id: 'company-1',
    name: 'Acme Corp',
    recruiter_id: 'user-1',
  } as never)
  healthGet.mockResolvedValue(mockHealth)
})

describe('AppRouter public routes', () => {
  it('renders home page at /', async () => {
    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'AI Recruitment Platform' }),
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
        screen.getByRole('heading', { name: 'Health Check' }),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Healthy')).toBeInTheDocument()
  })
})

describe('AppRouter role guards', () => {
  it('redirects anonymous users to /login for protected routes', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('401'))
    localStorage.removeItem('ai_recruitment_token')

    renderAt('/candidate/profile')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    })
  })

  it('lets a candidate access candidate portal', async () => {
    setUser('candidate')

    renderAt('/candidate/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Candidate Portal' }),
      ).toBeInTheDocument()
    })
  })

  it('blocks a candidate from recruiter portal', async () => {
    setUser('candidate')

    renderAt('/recruiter/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'AI Recruitment Platform' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Recruiter Portal' }),
    ).not.toBeInTheDocument()
  })

  it('lets a recruiter access recruiter portal', async () => {
    setUser('recruiter')

    renderAt('/recruiter/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Recruiter Portal' }),
      ).toBeInTheDocument()
    })
  })

  it('blocks a recruiter from candidate portal', async () => {
    setUser('recruiter')

    renderAt('/candidate/portal')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'AI Recruitment Platform' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Candidate Portal' }),
    ).not.toBeInTheDocument()
  })

  it('lets an admin access admin dashboard', async () => {
    setUser('admin')

    renderAt('/admin/dashboard')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Admin Dashboard' }),
      ).toBeInTheDocument()
    })
  })

  it('blocks an admin-only route for a recruiter', async () => {
    setUser('recruiter')

    renderAt('/admin/dashboard')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'AI Recruitment Platform' }),
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: 'Admin Dashboard' }),
    ).not.toBeInTheDocument()
  })
})

describe('AppRouter recruiter job routes', () => {
  it('renders interview generator for a recruiter', async () => {
    setUser('recruiter')

    renderAt('/recruiter/jobs/job-1/interview')

    await waitFor(() => {
      expect(screen.getByText('Số lượng câu hỏi')).toBeInTheDocument()
    })
    expect(mockedGetJobById).toHaveBeenCalledWith('job-1')
  })

  it('renders job recommendations for a recruiter', async () => {
    setUser('recruiter')

    renderAt('/recruiter/jobs/job-1/recommendations')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Gợi ý Ứng viên AI' }),
      ).toBeInTheDocument()
    })
    expect(mockedGetJobById).toHaveBeenCalledWith('job-1')
    expect(mockedGetCandidateRecommendations).toHaveBeenCalledWith(
      'job-1',
      10,
    )
  })
})

describe('AppRouter AI routes', () => {
  it('lets a candidate open the AI chat page', async () => {
    setUser('candidate')

    renderAt('/ai/chat')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Trợ lý AI' }),
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
        screen.getByRole('heading', { name: 'AI Recruitment Platform' }),
      ).toBeInTheDocument()
    })
  })
})

describe('AppRouter Navbar integration', () => {
  it('renders auth-specific nav links for a candidate', async () => {
    setUser('candidate')

    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'AI Recruitment Platform' }),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Trợ lý AI')).toBeInTheDocument()
    expect(screen.getByText('Tìm việc AI')).toBeInTheDocument()
    expect(screen.getByText('Gợi ý việc làm')).toBeInTheDocument()
  })

  it('renders recruiter nav links for a recruiter', async () => {
    setUser('recruiter')

    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'AI Recruitment Platform' }),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Trợ lý AI')).toBeInTheDocument()
    expect(screen.getByText('Quản lý tuyển dụng')).toBeInTheDocument()
    expect(screen.getByText('Tìm ứng viên AI')).toBeInTheDocument()
  })

  it('renders admin dashboard link for an admin', async () => {
    setUser('admin')

    renderAt('/')

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'AI Recruitment Platform' }),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Admin Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Quản lý tuyển dụng')).toBeInTheDocument()
  })
})
