import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { RegisterPage } from './RegisterPage'
import * as authApi from '@/api/auth'
import type { User } from '@/types/auth'

const mockUser: User = {
  id: 'user-1',
  email: 'candidate@example.com',
  role: 'candidate',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  getCurrentUser: vi.fn(),
  register: vi.fn(),
  createCandidateProfile: vi.fn(),
  createRecruiterProfile: vi.fn(),
}))

const mockedRegister = vi.mocked(authApi.register)

function renderRegisterPage() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

function fillValidForm() {
  fireEvent.change(screen.getByLabelText('Email'), {
    target: { value: 'candidate@example.com' },
  })
  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: 'password1' },
  })
  fireEvent.change(screen.getByLabelText('Confirm password'), {
    target: { value: 'password1' },
  })
  fireEvent.change(screen.getByLabelText('Role'), {
    target: { value: 'candidate' },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RegisterPage', () => {
  it('shows errors for empty fields', async () => {
    renderRegisterPage()

    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(screen.getByText('Email is required')).toBeInTheDocument()
      expect(screen.getByText('Password is required')).toBeInTheDocument()
      expect(
        screen.getByText('Please confirm your password'),
      ).toBeInTheDocument()
      expect(screen.getByText('Please select a role')).toBeInTheDocument()
    })
    expect(mockedRegister).not.toHaveBeenCalled()
  })

  it('shows invalid email error', async () => {
    renderRegisterPage()

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'not-an-email' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(
        screen.getByText('Enter a valid email address'),
      ).toBeInTheDocument()
    })
  })

  it('shows short password error', async () => {
    renderRegisterPage()

    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'short' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(
        screen.getByText('Password must be at least 8 characters'),
      ).toBeInTheDocument()
    })
  })

  it('shows password mismatch error', async () => {
    renderRegisterPage()

    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password1' },
    })
    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'different1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(
        screen.getByText('Passwords do not match'),
      ).toBeInTheDocument()
    })
  })

  it('requires role selection', async () => {
    renderRegisterPage()

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'candidate@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password1' },
    })
    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'password1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(screen.getByText('Please select a role')).toBeInTheDocument()
    })
  })

  it('registers successfully and navigates to login', async () => {
    mockedRegister.mockResolvedValue(mockUser)

    renderRegisterPage()

    fillValidForm()
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(mockedRegister).toHaveBeenCalledWith({
        email: 'candidate@example.com',
        password: 'password1',
        role: 'candidate',
      })
      expect(screen.getByText('Login Page')).toBeInTheDocument()
    })
  })

  it('shows conflict message on 400', async () => {
    const error = new Error('Email already registered')
    Object.assign(error, {
      response: { status: 400, data: { detail: 'Email already registered' } },
    })
    mockedRegister.mockRejectedValue(error)

    renderRegisterPage()

    fillValidForm()
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(
        screen.getByText('Email already registered'),
      ).toBeInTheDocument()
    })
  })
})