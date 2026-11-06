import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MyInterviewsPage } from './MyInterviewsPage'
import {
  getInterviewerApplication,
  listMyAssignedInterviews,
} from '@/api/interviews'
import type {
  AssignedInterview,
  InterviewerApplication,
} from '@/types/application'

vi.mock('@/api/interviews', () => ({
  listMyAssignedInterviews: vi.fn(),
  getInterviewerApplication: vi.fn(),
}))

const mockedList = vi.mocked(listMyAssignedInterviews)
const mockedApplication = vi.mocked(getInterviewerApplication)

const interview: AssignedInterview = {
  id: 'interview-1',
  application_id: 'application-1',
  scheduled_at: '2026-11-10T09:00:00Z',
  duration_minutes: 60,
  interview_type: 'technical',
  meeting_url: null,
  location: 'Room 3',
  status: 'scheduled',
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  job_id: 'job-1',
  job_title: 'Backend Engineer',
  company_name: 'Assignment Corp',
  candidate_name: 'Assigned Candidate',
  application_status: 'interviewing',
}

const application: InterviewerApplication = {
  id: 'application-1',
  job_id: 'job-1',
  job_title: 'Backend Engineer',
  company_name: 'Assignment Corp',
  status: 'interviewing',
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  candidate: {
    id: 'candidate-1',
    full_name: 'Assigned Candidate',
    title: 'Engineer',
    email: null,
    phone: null,
  },
  resume: {
    id: 'resume-1',
    title: 'Primary',
    is_primary: true,
    is_confirmed: true,
    parsed_data: {
      full_name: 'Assigned Candidate',
      email: null,
      phone: null,
      title: 'Engineer',
      summary: 'Backend engineer',
      total_years_experience: 5,
      skills: ['Python', 'FastAPI'],
      experiences: [],
      education: [],
      certifications: [],
      languages: [],
    },
  },
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MyInterviewsPage', () => {
  it('loads assigned interviews and masks direct contact details', async () => {
    mockedList.mockResolvedValue([interview])
    mockedApplication.mockResolvedValue(application)

    render(
      <MemoryRouter>
        <MyInterviewsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(mockedList).toHaveBeenCalledTimes(1)
    })
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    expect(screen.getAllByText('Assigned Candidate').length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(mockedApplication).toHaveBeenCalledWith('interview-1')
    })
    expect(screen.getByText('Email đã ẩn')).toBeInTheDocument()
    expect(screen.getByText('Số điện thoại đã ẩn')).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
  })

  it('shows an empty state when nothing is assigned', async () => {
    mockedList.mockResolvedValue([])

    render(
      <MemoryRouter>
        <MyInterviewsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(
        screen.getByText('Chưa có buổi phỏng vấn nào'),
      ).toBeInTheDocument()
    })
  })
})
