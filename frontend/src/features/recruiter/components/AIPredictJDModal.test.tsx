import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AIPredictJDModal } from './AIPredictJDModal'
import apiClient from '@/api/client'
import type { ParsedJob } from './AIPredictJDModal'

const mockParsedJob: ParsedJob = {
  title: 'Senior Frontend Engineer',
  summary: 'Build modern web applications with React.',
  required_skills: ['React', 'TypeScript'],
  preferred_skills: ['Next.js'],
  minimum_years_experience: 3,
  education_level: 'Bachelor degree',
}

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

const mockedPost = vi.mocked(apiClient.post)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AIPredictJDModal', () => {
  it('requires raw JD input before parsing', async () => {
    render(<AIPredictJDModal onClose={vi.fn()} />)

    fireEvent.click(
      screen.getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
    )

    await waitFor(() => {
      expect(
        screen.getByText('Please paste the job description first.'),
      ).toBeInTheDocument()
    })
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it('calls parse-jd with the raw JD and job title', async () => {
    mockedPost.mockResolvedValue(mockParsedJob as never)

    render(<AIPredictJDModal onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/Job title/i), {
      target: { value: 'Senior Frontend Engineer' },
    })
    fireEvent.change(screen.getByLabelText(/Raw job description/i), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(
      screen.getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/ai/parse-jd', {
        job_title: 'Senior Frontend Engineer',
        job_description: 'Build modern web applications with React.',
        job_id: null,
      })
    })
  })

  it('renders the parsed job schema', async () => {
    mockedPost.mockResolvedValue(mockParsedJob as never)

    render(<AIPredictJDModal onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/Raw job description/i), {
      target: { value: 'Build modern web applications with React.' },
    })

    fireEvent.click(
      screen.getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Senior Frontend Engineer')).toBeInTheDocument()
      expect(screen.getByText('React')).toBeInTheDocument()
      expect(screen.getByText('TypeScript')).toBeInTheDocument()
      expect(screen.getByText('Next.js')).toBeInTheDocument()
      expect(screen.getByText(/3 years/)).toBeInTheDocument()
      expect(screen.getByText('Bachelor degree')).toBeInTheDocument()
    })
  })

  it('enables "Apply to Form" after parsing', async () => {
    mockedPost.mockResolvedValue(mockParsedJob as never)

    render(<AIPredictJDModal onClose={vi.fn()} />)

    const applyButton = screen.getByRole('button', {
      name: /Áp dụng vào Form/i,
    })
    expect(applyButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/Raw job description/i), {
      target: { value: 'Build modern web applications with React.' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
    )

    await waitFor(() => {
      expect(applyButton).toBeEnabled()
    })
  })

  it('calls onApply with the parsed job', async () => {
    mockedPost.mockResolvedValue(mockParsedJob as never)
    const onApply = vi.fn()

    render(<AIPredictJDModal onClose={vi.fn()} onApply={onApply} />)

    fireEvent.change(screen.getByLabelText(/Raw job description/i), {
      target: { value: 'Build modern web applications with React.' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
    )

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Áp dụng vào Form/i }),
      ).toBeEnabled()
    })

    fireEvent.click(
      screen.getByRole('button', { name: /Áp dụng vào Form/i }),
    )

    await waitFor(() => {
      expect(onApply).toHaveBeenCalledWith(mockParsedJob)
    })
  })

  it('shows error when parsing fails', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 400, data: { detail: 'Empty document' } },
    })
    mockedPost.mockRejectedValue(error)

    render(<AIPredictJDModal onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/Raw job description/i), {
      target: { value: 'Build modern web applications with React.' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: /AI Bóc Tách Kỹ Năng/i }),
    )

    await waitFor(() => {
      expect(screen.getByText('Empty document')).toBeInTheDocument()
    })
  })
})