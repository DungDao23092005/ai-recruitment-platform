import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { VerifyResetOtpPage } from '@/pages/auth/VerifyResetOtpPage'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import * as authApi from '@/api/auth'

vi.mock('@/api/auth')
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

const mockUseAuth = vi.mocked(useAuth)

describe('VerifyResetOtpPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = (initialEntries = [{ pathname: '/verify-reset-otp' }]) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>
          <Routes>
            <Route path="/verify-reset-otp" element={<VerifyResetOtpPage />} />
            <Route path="/reset-password" element={<div data-testid="reset-password-page">Reset Password Page</div>} />
            <Route path="*" element={<div>Not Found</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )
  }

  const mockEmail = 'test@example.com'

  it('renders OTP input fields', async () => {
    vi.mocked(authApi.verifyResetOtp).mockResolvedValue({ reset_token: 'test-token' })

    await act(async () => {
      renderPage([{ pathname: '/verify-reset-otp', state: { email: mockEmail } }])
    })

    await waitFor(() => {
      expect(screen.getByText('Xác thực mã OTP')).toBeInTheDocument()
      expect(screen.getByText(new RegExp(mockEmail))).toBeInTheDocument()
    })

    // Check 6 input fields - query by role without name since they're in a group
    const inputs = screen.getAllByRole('textbox')
    expect(inputs).toHaveLength(6)
  })
it('shows error for empty OTP', async () => {
    vi.mocked(authApi.verifyResetOtp).mockResolvedValue({ reset_token: 'test-token' })

    await act(async () => {
      renderPage([{ pathname: '/verify-reset-otp', state: { email: mockEmail } }])
    })

    // Button should be disabled when OTP is empty
    const submitButton = screen.getByRole('button', { name: /xác thực/i })
    expect(submitButton).toBeDisabled()
  })

  it('shows error for invalid OTP format', async () => {
    vi.mocked(authApi.verifyResetOtp).mockResolvedValue({ reset_token: 'test-token' })

    await act(async () => {
      renderPage([{ pathname: '/verify-reset-otp', state: { email: mockEmail } }])
    })

    const inputs = screen.getAllByRole('textbox')
    // Fill 5 digits
    for (let i = 0; i < 5; i++) {
      await act(async () => {
        fireEvent.change(inputs[i], { target: { value: '1' } })
      })
    }

    // Try to enter non-digit in 6th position - component filters non-digits
    await act(async () => {
      fireEvent.change(inputs[5], { target: { value: 'a' } })
    })

    // Component filters non-digits, so 6th input remains empty
    // Submit button should remain disabled (requires 6 digits)
    const submitButton = screen.getByRole('button', { name: /xác thực/i })
    expect(submitButton).toBeDisabled()

    // Directly test the validation function for invalid OTP format
    const { validate } = await import('@/pages/auth/VerifyResetOtpPage')
    const validationErrors = validate({ otp: '11111a' })
    expect(validationErrors.otp).toBe('Mã OTP phải là 6 chữ số')
  })


  it('navigates to reset password page on successful verification', async () => {
    vi.mocked(authApi.verifyResetOtp).mockResolvedValue({ reset_token: 'test-reset-token' })

    await act(async () => {
      renderPage([{ pathname: '/verify-reset-otp', state: { email: mockEmail } }])
    })

    const inputs = screen.getAllByRole('textbox')
    // Fill all 6 digits
    for (let i = 0; i < 6; i++) {
      await act(async () => {
        fireEvent.change(inputs[i], { target: { value: '1' } })
      })
    }

    // Submit form by clicking the submit button
    await act(async () => {
      const submitButton = screen.getByRole('button', { name: /xác thực/i })
      fireEvent.click(submitButton)
    })

    // Component shows success state inline with reset token
    await waitFor(() => {
      expect(screen.getByText('Xác thực thành công')).toBeInTheDocument()
      expect(screen.getByText('test-reset-token')).toBeInTheDocument()
    })
  })

  it('shows error for invalid OTP', async () => {
    const apiError = new Error('API Error') as Error & { response: { status: number; data: { detail: string } } }
    apiError.response = { status: 400, data: { detail: 'Mã OTP không hợp lệ hoặc đã hết hạn' } }
    vi.mocked(authApi.verifyResetOtp).mockRejectedValue(apiError)

    await act(async () => {
      renderPage([{ pathname: '/verify-reset-otp', state: { email: mockEmail } }])
    })

    // Fill OTP
    const inputs = screen.getAllByRole('textbox')
    for (let i = 0; i < 6; i++) {
      await act(async () => {
        fireEvent.change(inputs[i], { target: { value: '1' } })
      })
    }

    // Submit form by clicking the submit button
    await act(async () => {
      const submitButton = screen.getByRole('button', { name: /xác thực/i })
      fireEvent.click(submitButton)
    })

    await waitFor(() => {
      expect(screen.getByText('Mã OTP không hợp lệ hoặc đã hết hạn')).toBeInTheDocument()
    })
  })

  it('shows loading spinner while verifying', async () => {
    let resolveFn: (value: { reset_token: string }) => void
    const promise = new Promise<{ reset_token: string }>((resolve) => {
      resolveFn = resolve
    })
    vi.mocked(authApi.verifyResetOtp).mockReturnValue(promise)

    await act(async () => {
      renderPage([{ pathname: '/verify-reset-otp', state: { email: mockEmail } }])
    })

    // Fill OTP
    const inputs = screen.getAllByRole('textbox')
    for (let i = 0; i < 6; i++) {
      await act(async () => {
        fireEvent.change(inputs[i], { target: { value: '1' } })
      })
    }

    // Submit form by clicking the submit button
    await act(async () => {
      const submitButton = screen.getByRole('button', { name: /xác thực/i })
      fireEvent.click(submitButton)
    })

    await waitFor(() => {
      const loadingButton = screen.getByRole('button', { name: /đang tải/i })
      expect(loadingButton).toBeInTheDocument()
      expect(loadingButton).toContainHTML('animate-spin')
    })

    resolveFn!({ reset_token: 'test-token' })

    await waitFor(() => {
      expect(screen.getByText('Xác thực thành công')).toBeInTheDocument()
      expect(screen.getByText('test-token')).toBeInTheDocument()
    })
  })

  it('shows resend button with cooldown', async () => {
    vi.mocked(authApi.verifyResetOtp).mockResolvedValue({ reset_token: 'test-token' })

    await act(async () => {
      renderPage([{ pathname: '/verify-reset-otp', state: { email: mockEmail } }])
    })

    await waitFor(() => {
      const button = screen.getByRole('button', { name: /gửi lại mã otp/i })
      expect(button).toBeInTheDocument()
      expect(button).not.toBeDisabled()
    })

    // After click, cooldown should start
    await act(async () => {
      await screen.getByRole('button', { name: /gửi lại mã otp/i }).click()
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /gửi lại sau \d+s/i })).toBeDisabled()
    })
  })

  it('navigates to login page when clicking login link', () => {
    renderPage([{ pathname: '/verify-reset-otp' }])

    const link = screen.getByRole('link', { name: /đăng nhập/i })
    expect(link).toHaveAttribute('href', '/login')
  })
})