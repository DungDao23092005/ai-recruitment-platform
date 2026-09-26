/// <reference types="vitest/globals" />
import { render, screen, waitFor, act } from '@testing-library/react';
import { BrowserRouter, MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotificationBell } from '@/components/common/NotificationBell';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';
import { useNotificationStream } from '@/hooks/useNotificationStream';

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('@/hooks/useNotificationStream', () => ({
  useNotificationStream: vi.fn(),
}));

vi.mock('@/stores/useUnreadCountStore', () => ({
  useUnreadCountStore: vi.fn(),
}));

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useNotificationStream).mockReturnValue({ isConnected: false });
  });

  const renderWithRouter = (component: React.ReactNode) => {
    return render(
      <BrowserRouter>
        <AuthProvider>{component}</AuthProvider>
      </BrowserRouter>
    );
  };

  it('renders null when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 0,
      setUnreadCount: vi.fn(),
      increment: vi.fn(),
      decrement: vi.fn(),
      reset: vi.fn(),
    });

    renderWithRouter(<NotificationBell />);
    expect(screen.queryByRole('button', { name: /thông báo/i })).not.toBeInTheDocument();
  });

  it('renders null when loading', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      currentUser: null,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 0,
      setUnreadCount: vi.fn(),
      increment: vi.fn(),
      decrement: vi.fn(),
      reset: vi.fn(),
    });

    renderWithRouter(<NotificationBell />);
    expect(screen.queryByRole('button', { name: /thông báo/i })).not.toBeInTheDocument();
  });

  it('renders bell icon when authenticated with 0 unread', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 0,
      setUnreadCount: vi.fn(),
      increment: vi.fn(),
      decrement: vi.fn(),
      reset: vi.fn(),
    });

    renderWithRouter(<NotificationBell />);

    expect(screen.getByRole('button', { name: /thông báo$/i })).toBeInTheDocument();
  });

  it('shows unread count badge when count > 0', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 5,
      setUnreadCount: vi.fn(),
      increment: vi.fn(),
      decrement: vi.fn(),
      reset: vi.fn(),
    });

    renderWithRouter(<NotificationBell />);

    const button = screen.getByRole('button', { name: /thông báo, 5 chưa đọc/i });
    expect(button).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('shows 99+ when count > 99', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 150,
      setUnreadCount: vi.fn(),
      increment: vi.fn(),
      decrement: vi.fn(),
      reset: vi.fn(),
    });

    renderWithRouter(<NotificationBell />);

    expect(screen.getByText('99+')).toBeInTheDocument();
  });

  it('navigates to /notifications on click', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 0,
      setUnreadCount: vi.fn(),
      increment: vi.fn(),
      decrement: vi.fn(),
      reset: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/candidate/portal']}>
        <AuthProvider>
          <Routes>
            <Route path="/notifications" element={<div data-testid="notifications-page">Notifications Page</div>} />
            <Route path="*" element={<NotificationBell />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      const button = screen.getByRole('button', { name: /thông báo$/i });
      expect(button).toBeInTheDocument();
    });

    await act(async () => {
      screen.getByRole('button', { name: /thông báo$/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('notifications-page')).toBeInTheDocument();
    });
  });

  it('does not use window.location.href for navigation', async () => {
    const originalLocation = window.location;
    delete (window as any).location;
    window.location = { href: '' } as any;

    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 0,
      setUnreadCount: vi.fn(),
      increment: vi.fn(),
      decrement: vi.fn(),
      reset: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/candidate/portal']}>
        <AuthProvider>
          <Routes>
            <Route path="/notifications" element={<div data-testid="notifications-page">Notifications Page</div>} />
            <Route path="*" element={<NotificationBell />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      const button = screen.getByRole('button', { name: /thông báo$/i });
      expect(button).toBeInTheDocument();
    });

    await act(async () => {
      screen.getByRole('button', { name: /thông báo$/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('notifications-page')).toBeInTheDocument();
    });

    expect(window.location.href).toBe('');
    window.location = originalLocation;
  });
});
