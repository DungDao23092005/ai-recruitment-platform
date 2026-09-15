import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { CandidateRecommendationsPage } from './CandidateRecommendationsPage'
import * as aiApi from '@/api/ai'
import * as authApi from '@/api/auth'
import type { JobMatchRecommendation } from '@/types/ai'
import type { CandidateProfileRead } from '@/types/auth'

const mockRecommendations: JobMatchRecommendation[] = [
  {
    job_id: 'job-1',
    parsed_job: {
      title: 'Senior Frontend Engineer',
      summary: 'Build modern web applications.',
      required_skills: ['React', 'TypeScript'],
      preferred_skills: [],
      minimum_years_experience: 4,
      education_level: null,
    },
    match_result: {
      overall_score: 82,
      cosine_similarity: 0.85,
      skill_coverage_score: 0.8,
      experience_match_score: 0.75,
      matching_skills: ['React', 'TypeScript'],
      skill_gap: ['GraphQL'],
      match_reasons: ['Strong skill overlap'],
    },
  },
  {
    job_id: 'job-2',
    parsed_job: {
      title: 'Backend Engineer',
      summary: 'Build scalable services.',
      required_skills: ['Python', 'FastAPI'],
      preferred_skills: [],
      minimum_years_experience: 3,
      education_level: null,
    },
    match_result: {
      overall_score: 91,
      cosine_similarity: 0.92,
      skill_coverage_score: 0.9,
      experience_match_score: 0.85,
      matching_skills: ['Python', 'FastAPI'],
      skill_gap: ['Docker'],
      match_reasons: ['Excellent overlap'],
    },
  },
]

const mockCandidateProfile: CandidateProfileRead = {
  id: 'candidate-1',
  user_id: 'user-1',
  full_name: 'Jane Doe',
  phone: null,
  title: 'Software Engineer',
}

vi.mock('@/api/ai', () => ({
  getJobRecommendations: vi.fn(),
  getCandidateRecommendations: vi.fn(),
  matchCandidateWithJob: vi.fn(),
  parseResume: vi.fn(),
  getMyResume: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  getCandidateProfile: vi.fn(),
}))

const mockedGetJobRecommendations = vi.mocked(aiApi.getJobRecommendations)
const mockedGetMyResume = vi.mocked(aiApi.getMyResume)
const mockedGetCandidateProfile = vi.mocked(authApi.getCandidateProfile)

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/candidate/recommendations']}>
      <Routes>
        <Route
          path="/candidate/recommendations"
          element={<CandidateRecommendationsPage />}
        />
        <Route path="/candidate/cv-upload" element={<div>CV Upload</div>} />
        <Route path="/candidate/profile" element={<div>Profile</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedGetMyResume.mockResolvedValue({ parsed_data: null })
})

describe('CandidateRecommendationsPage', () => {
  it('calls getJobRecommendations on mount', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: mockRecommendations, hasCV: true })

    renderPage()

    await waitFor(() => {
      expect(mockedGetJobRecommendations).toHaveBeenCalledWith(10)
    })
  })

  it('shows the loading state while fetching', async () => {
    let resolve!: (value: { recommendations: JobMatchRecommendation[]; hasCV: boolean }) => void
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )

    const { container } = renderPage()

    await waitFor(() => {
      expect(container.querySelector('.animate-pulse')).not.toBeNull()
    })

    resolve({ recommendations: mockRecommendations, hasCV: true })
  })

  it('renders recommendation cards on success', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: mockRecommendations, hasCV: true })

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
      expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    })
  })

  it('sorts recommendations by score descending', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: mockRecommendations, hasCV: true })

    renderPage()

    await waitFor(() => {
      const scoreBadges = screen
        .getAllByLabelText(/điểm đối sánh \d+ phần trăm/i)
        .map((el) => Number(el.textContent?.replace('%', '')))
      expect(scoreBadges).toEqual([91, 82])
    })
  })

  it('links recommendation cards to the candidate job detail route', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: mockRecommendations, hasCV: true })

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })

    const detailLinks = screen.getAllByRole('link', {
      name: /Xem chi tiết & Nộp đơn/i,
    })
    expect(detailLinks[0]).toHaveAttribute('href', '/candidate/jobs/job-2')
    expect(detailLinks[1]).toHaveAttribute('href', '/candidate/jobs/job-1')
  })

  it('shows the empty state with a CV upload CTA when hasCV is false', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: [], hasCV: false })

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText(
          /Chưa có CV/i,
        ),
      ).toBeInTheDocument()
    })

    const link = screen.getByRole('link', { name: /Tải lên CV/i })
    expect(link).toHaveAttribute('href', '/candidate/cv-upload')
  })

  it('shows missing profile state when candidate profile not found', async () => {
    const error = new Error('Not Found')
    Object.assign(error, {
      response: { status: 404, data: { detail: 'Candidate profile not found' } },
    })
    mockedGetCandidateProfile.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Hồ sơ ứng viên chưa được tạo'),
      ).toBeInTheDocument()
    })

    // Should NOT call getJobRecommendations or getMyResume when profile is missing
    expect(mockedGetJobRecommendations).not.toHaveBeenCalled()
    expect(mockedGetMyResume).not.toHaveBeenCalled()

    const link = screen.getByRole('link', { name: /Tạo hồ sơ ứng viên/i })
    expect(link).toHaveAttribute('href', '/candidate/profile')
  })

  it('shows recommendations when profile exists but resume is missing (404)', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: mockRecommendations, hasCV: true })
    const error = new Error('Not Found')
    Object.assign(error, {
      response: { status: 404, data: { detail: 'Resume not found' } },
    })
    mockedGetMyResume.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
    })

    // Should NOT show generic error state
    expect(screen.queryByText(/Server error/i)).not.toBeInTheDocument()
    // Should NOT show error banner
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows recommendations when profile and resume exist', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: mockRecommendations, hasCV: true })
    mockedGetMyResume.mockResolvedValue({ parsed_data: { skills: ['React'] } })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
    })
  })

  it('shows error banner when recommendation API returns 500', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    const error = new Error('Server Error')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetJobRecommendations.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    // Should NOT be treated as missing profile
    expect(screen.queryByText('Hồ sơ ứng viên chưa được tạo')).not.toBeInTheDocument()
  })

  it('shows error banner when resume API returns 500', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: mockRecommendations, hasCV: true })
    const error = new Error('Server Error')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Resume server error' } },
    })
    mockedGetMyResume.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Resume server error')).toBeInTheDocument()
    })

    // Should NOT be treated as missing profile
    expect(screen.queryByText('Hồ sơ ứng viên chưa được tạo')).not.toBeInTheDocument()
    // Should NOT treat resume 500 as missing CV
    expect(screen.queryByText(/Chưa có CV/i)).not.toBeInTheDocument()
  })

  it('shows a friendly error and retries on 500', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetJobRecommendations
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce({ recommendations: mockRecommendations, hasCV: true })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Senior Frontend Engineer'),
      ).toBeInTheDocument()
    })
  })

  it('requests stop after profile 404 - no recommendation or resume requests', async () => {
    const error = new Error('Not Found')
    Object.assign(error, {
      response: { status: 404, data: { detail: 'Candidate profile not found' } },
    })
    mockedGetCandidateProfile.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(mockedGetCandidateProfile).toHaveBeenCalledTimes(1)
      expect(mockedGetJobRecommendations).not.toHaveBeenCalled()
      expect(mockedGetMyResume).not.toHaveBeenCalled()
    })
  })

  it('requests recommendation and resume after profile success', async () => {
    mockedGetCandidateProfile.mockResolvedValue({
      id: 'candidate-1',
      user_id: 'user-1',
      full_name: 'Jane Doe',
      phone: null,
      title: 'Software Engineer',
    })
    mockedGetJobRecommendations.mockResolvedValue({ recommendations: mockRecommendations, hasCV: true })
    mockedGetMyResume.mockResolvedValue({ parsed_data: null })

    renderPage()

    await waitFor(() => {
      expect(mockedGetCandidateProfile).toHaveBeenCalledTimes(1)
      expect(mockedGetJobRecommendations).toHaveBeenCalledTimes(1)
      expect(mockedGetMyResume).toHaveBeenCalledTimes(1)
    })
  })
})