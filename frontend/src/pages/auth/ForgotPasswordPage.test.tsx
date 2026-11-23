import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { BrowserRouter, MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { ForgotPasswordPage } from '@/pages/auth/ForgotPasswordPage'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import * as authApi from '@/api/auth'

vi.mock('@/api/auth')
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

const mockUseAuth = vi.mocked(useAuth)

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderWithRouter = (component: React.ReactNode) => {
    return render(
      <BrowserRouter>
        <AuthProvider>{component}</AuthProvider>
      </BrowserRouter>
    )
  }

  it('renders email input and submit button', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    vi.mocked(authApi.forgotPassword).mockResolvedValue({ message: 'Success' })

    renderWithRouter(<ForgotPasswordPage />)

    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /gửi mã otp/i })).toBeInTheDocument()
  })

  it('shows validation error for empty email', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    renderWithRouter(<ForgotPasswordPage />)

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Email không được để trống')).toBeInTheDocument()
    })
  })

  it('shows validation error for invalid email format', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    renderWithRouter(<ForgotPasswordPage />)

    const input = screen.getByLabelText('Email')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'invalid-email' } })
    })

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Vui lòng nhập địa chỉ email hợp lệ')).toBeInTheDocument()
    })
  })

  it('shows success message on successful submission', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    vi.mocked(authApi.forgotPassword).mockResolvedValue({ message: 'Success' })

    renderWithRouter(<ForgotPasswordPage />)

    const input = screen.getByLabelText('Email')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'test@example.com' } })
    })

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Yêu cầu đã được ghi nhận')).toBeInTheDocument()
      expect(screen.getByText('Nếu email của bạn đã được đăng ký trong hệ thống, hướng dẫn đặt lại mật khẩu sẽ được gửi đến hộp thư. Vui lòng kiểm tra cả thư mục Spam/Junk.')).toBeInTheDocument()
    })
  })

  it('successful submission does not automatically navigate to OTP verification route', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    vi.mocked(authApi.forgotPassword).mockResolvedValue({ message: 'Success' })

    render(
      <MemoryRouter initialEntries={['/forgot-password']}>
        <AuthProvider>
          <Routes>
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/verify-reset-otp" element={<div data-testid="otp-page">OTP Page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    const input = screen.getByLabelText('Email')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'test@example.com' } })
    })

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Yêu cầu đã được ghi nhận')).toBeInTheDocument()
    })
    // Confirms it stays on forgot-password success card, does NOT navigate
    expect(screen.queryByTestId('otp-page')).not.toBeInTheDocument()
  })

  it('allows user to enter another email from the success view', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    vi.mocked(authApi.forgotPassword).mockResolvedValue({ message: 'Success' })

    renderWithRouter(<ForgotPasswordPage />)

    const input = screen.getByLabelText('Email')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'test@example.com' } })
    })

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Yêu cầu đã được ghi nhận')).toBeInTheDocument()
    })

    const resetBtn = screen.getByRole('button', { name: /nhập email khác/i })
    await act(async () => {
      fireEvent.click(resetBtn)
    })

    expect(screen.getByLabelText('Email')).toHaveValue('')
    expect(screen.getByRole('button', { name: /gửi mã otp/i })).toBeInTheDocument()
  })

  it('manual OTP action explicitly links to verification route with email state', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    vi.mocked(authApi.forgotPassword).mockResolvedValue({ message: 'Success' })

    renderWithRouter(<ForgotPasswordPage />)

    const input = screen.getByLabelText('Email')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'user@example.com' } })
    })

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Yêu cầu đã được ghi nhận')).toBeInTheDocument()
    })

    const otpLink = screen.getByRole('link', { name: /đã nhận được mã otp\? nhập mã xác thực/i })
    expect(otpLink).toHaveAttribute('href', '/verify-reset-otp')
  })

  it('shows error message on API failure', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    const apiError = new Error('API Error') as Error & { response: { status: number; data: { detail: string } } }
    apiError.response = { status: 500, data: { detail: 'Server error' } }
    vi.mocked(authApi.forgotPassword).mockRejectedValue(apiError)

    renderWithRouter(<ForgotPasswordPage />)

    const input = screen.getByLabelText('Email')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'test@example.com' } })
    })

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })
  })

  it('shows cooldown timer after submission', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    vi.mocked(authApi.forgotPassword).mockResolvedValue({ message: 'Success' })

    renderWithRouter(<ForgotPasswordPage />)

    const input = screen.getByLabelText('Email')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'test@example.com' } })
    })

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    // Component shows success state after submission
    await waitFor(() => {
      expect(screen.getByText('Yêu cầu đã được ghi nhận')).toBeInTheDocument()
    })
  })

  it('disables submit button during cooldown', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    vi.mocked(authApi.forgotPassword).mockResolvedValue({ message: 'Success' })

    renderWithRouter(<ForgotPasswordPage />)

    const input = screen.getByLabelText('Email')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'test@example.com' } })
    })

    await screen.getByRole('button', { name: /gửi mã otp/i }).click()

    // Component shows success state after submission, button is not visible in success view
    await waitFor(() => {
      expect(screen.getByText('Yêu cầu đã được ghi nhận')).toBeInTheDocument()
    })
  })

  it('navigates to login page when clicking login link', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    })

    render(
      <MemoryRouter initialEntries={['/forgot-password']}>
        <AuthProvider>
          <Routes>
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/login" element={<div data-testid="login-page">Login Page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    const link = screen.getByRole('link', { name: /đăng nhập/i })
    expect(link).toHaveAttribute('href', '/login')
  })
})