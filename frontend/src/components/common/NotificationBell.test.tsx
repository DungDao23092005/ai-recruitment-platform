/// <reference types="vitest/globals" />
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter, MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotificationBell } from '@/components/common/NotificationBell';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import * as notificationsApi from '@/api/notifications';

vi.mock('@/api/notifications');
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

    renderWithRouter(<NotificationBell />);
    expect(screen.queryByRole('button', { name: /thông báo/i })).not.toBeInTheDocument();
  });

  it('renders bell icon when authenticated with 0 unread', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getUnreadNotificationCount).mockResolvedValue({
      unread_count: 0,
    });

    renderWithRouter(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /thông báo$/i })).toBeInTheDocument();
    });
  });

  it('shows unread count badge when count > 0', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getUnreadNotificationCount).mockResolvedValue({
      unread_count: 5,
    });

    renderWithRouter(<NotificationBell />);

    await waitFor(() => {
      const button = screen.getByRole('button', { name: /thông báo, 5 chưa đọc/i });
      expect(button).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
    });
  });

  it('shows 99+ when count > 99', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getUnreadNotificationCount).mockResolvedValue({
      unread_count: 150,
    });

    renderWithRouter(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByText('99+')).toBeInTheDocument();
    });
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

    vi.mocked(notificationsApi.getUnreadNotificationCount).mockResolvedValue({
      unread_count: 0,
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

    await screen.getByRole('button', { name: /thông báo$/i }).click();

    await waitFor(() => {
      expect(screen.getByTestId('notifications-page')).toBeInTheDocument();
    });
  });

  it('shows loading spinner while fetching', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    let resolveFn: (value: { unread_count: number }) => void;
    const promise = new Promise<{ unread_count: number }>((resolve) => {
      resolveFn = resolve;
    });
    vi.mocked(notificationsApi.getUnreadNotificationCount).mockReturnValue(promise);

    renderWithRouter(<NotificationBell />);

    await waitFor(() => {
      const button = screen.getByRole('button', { name: /thông báo$/i });
      expect(button).toBeInTheDocument();
    });

    expect(screen.getByRole('button')).toContainHTML('animate-spin');

    resolveFn!({ unread_count: 3 });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /thông báo, 3 chưa đọc/i })).toBeInTheDocument();
    });
  });
});