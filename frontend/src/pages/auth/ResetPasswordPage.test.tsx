import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { ResetPasswordPage } from '@/pages/auth/ResetPasswordPage'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import * as authApi from '@/api/auth'

vi.mock('@/api/auth')
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

const mockUseAuth = vi.mocked(useAuth)

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = (initialEntries = [{ pathname: '/reset-password' }]) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>
          <Routes>
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/login" element={<div data-testid="login-page">Login Page</div>} />
            <Route path="*" element={<div>Not Found</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )
  }

  const renderPageWithToken = () => {
    return render(
      <MemoryRouter initialEntries={[{ pathname: '/reset-password', state: { resetToken: 'test-reset-token', email: 'test@example.com' } }]}>
        <AuthProvider>
          <Routes>
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/login" element={<div data-testid="login-page">Login Page</div>} />
            <Route path="*" element={<div>Not Found</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )
  }

  it('renders password and confirm password fields', () => {
    renderPageWithToken()

    expect(screen.getByLabelText('Mật khẩu mới')).toBeInTheDocument()
    expect(screen.getByLabelText('Xác nhận mật khẩu mới')).toBeInTheDocument()
  })

  it('shows validation error for empty password', async () => {
    renderPageWithToken()

    await screen.getByRole('button', { name: /cập nhật mật khẩu/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Mật khẩu mới không được để trống')).toBeInTheDocument()
    })
  })

  it('shows validation error for short password', async () => {
    renderPageWithToken()

    const passwordInput = screen.getByLabelText('Mật khẩu mới')
    await act(async () => {
      fireEvent.change(passwordInput, { target: { value: 'short' } })
    })

    await screen.getByRole('button', { name: /cập nhật mật khẩu/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Mật khẩu phải có ít nhất 8 ký tự')).toBeInTheDocument()
    })
  })

  it('shows validation error for mismatched passwords', async () => {
    renderPageWithToken()

    const passwordInput = screen.getByLabelText('Mật khẩu mới')
    await act(async () => {
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
    })

    const confirmInput = screen.getByLabelText('Xác nhận mật khẩu mới')
    await act(async () => {
      fireEvent.change(confirmInput, { target: { value: 'different' } })
    })

    await screen.getByRole('button', { name: /cập nhật mật khẩu/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Mật khẩu xác nhận không khớp')).toBeInTheDocument()
    })
  })

  it('shows error for invalid reset token', async () => {
    const apiError = new Error('API Error') as Error & { response: { status: number; data: { detail: string } } }
    apiError.response = { status: 400, data: { detail: 'Mã đặt lại mật khẩu không hợp lệ hoặc đã hết hạn' } }
    vi.mocked(authApi.resetPassword).mockRejectedValue(apiError)

    renderPageWithToken()

    const passwordInput = screen.getByLabelText('Mật khẩu mới')
    await act(async () => {
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
    })

    const confirmInput = screen.getByLabelText('Xác nhận mật khẩu mới')
    await act(async () => {
      fireEvent.change(confirmInput, { target: { value: 'password123' } })
    })

    await screen.getByRole('button', { name: /cập nhật mật khẩu/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Mã đặt lại mật khẩu không hợp lệ hoặc đã hết hạn')).toBeInTheDocument()
    })
  })

  it('shows success message on successful password reset', async () => {
    vi.mocked(authApi.resetPassword).mockResolvedValue({ message: 'Success' })

    renderPageWithToken()

    const passwordInput = screen.getByLabelText('Mật khẩu mới')
    await act(async () => {
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
    })

    const confirmInput = screen.getByLabelText('Xác nhận mật khẩu mới')
    await act(async () => {
      fireEvent.change(confirmInput, { target: { value: 'password123' } })
    })

    await screen.getByRole('button', { name: /cập nhật mật khẩu/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Đặt lại mật khẩu thành công')).toBeInTheDocument()
      expect(screen.getByText('Mật khẩu của bạn đã được cập nhật. Vui lòng đăng nhập lại với mật khẩu mới.')).toBeInTheDocument()
    })
  })

  it('shows loading state while resetting password', async () => {
    let resolveFn: (value: { message: string }) => void
    const promise = new Promise<{ message: string }>((resolve) => {
      resolveFn = resolve
    })
    vi.mocked(authApi.resetPassword).mockReturnValue(promise)

    renderPageWithToken()

    const passwordInput = screen.getByLabelText('Mật khẩu mới')
    await act(async () => {
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
    })

    const confirmInput = screen.getByLabelText('Xác nhận mật khẩu mới')
    await act(async () => {
      fireEvent.change(confirmInput, { target: { value: 'password123' } })
    })

    await screen.getByRole('button', { name: /cập nhật mật khẩu/i }).click()

    await waitFor(() => {
      const loadingButton = screen.getByRole('button', { name: /đang tải/i })
      expect(loadingButton).toBeInTheDocument()
      expect(loadingButton).toContainHTML('animate-spin')
    })

    resolveFn!({ message: 'Success' })

    await waitFor(() => {
      expect(screen.getByText('Đặt lại mật khẩu thành công')).toBeInTheDocument()
    })
  })

  it('toggles password visibility', () => {
    renderPageWithToken()

    const passwordInput = screen.getByLabelText('Mật khẩu mới')
    expect(passwordInput).toHaveAttribute('type', 'password')

    const toggleButtons = screen.getAllByRole('button', { name: /hiện mật khẩu/i })
    fireEvent.click(toggleButtons[0])

    expect(screen.getByLabelText('Mật khẩu mới')).toHaveAttribute('type', 'text')

    fireEvent.click(toggleButtons[0])

    expect(screen.getByLabelText('Mật khẩu mới')).toHaveAttribute('type', 'password')
  })

  it('shows success state on successful password reset', async () => {
    vi.mocked(authApi.resetPassword).mockResolvedValue({ message: 'Success' })

    render(
      <MemoryRouter initialEntries={[{ pathname: '/reset-password', state: { resetToken: 'test-token', email: 'test@example.com' } }]}>
        <AuthProvider>
          <Routes>
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/login" element={<div data-testid="login-page">Login Page</div>} />
            <Route path="*" element={<div>Not Found</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    const passwordInput = screen.getByLabelText('Mật khẩu mới')
    await act(async () => {
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
    })

    const confirmInput = screen.getByLabelText('Xác nhận mật khẩu mới')
    await act(async () => {
      fireEvent.change(confirmInput, { target: { value: 'password123' } })
    })

    await screen.getByRole('button', { name: /cập nhật mật khẩu/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Đặt lại mật khẩu thành công')).toBeInTheDocument()
    })
  })

  it('shows error for missing reset token', async () => {
    renderPage()

    // Fill form and submit to trigger error
    const passwordInput = screen.getByLabelText('Mật khẩu mới')
    await act(async () => {
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
    })

    const confirmInput = screen.getByLabelText('Xác nhận mật khẩu mới')
    await act(async () => {
      fireEvent.change(confirmInput, { target: { value: 'password123' } })
    })

    await screen.getByRole('button', { name: /cập nhật mật khẩu/i }).click()

    await waitFor(() => {
      expect(screen.getByText('Mã đặt lại mật khẩu không hợp lệ. Vui lòng thử lại từ đầu.')).toBeInTheDocument()
    })
  })
})