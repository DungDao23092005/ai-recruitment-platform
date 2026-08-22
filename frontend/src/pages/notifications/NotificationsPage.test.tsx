/// <reference types="vitest/globals" />
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotificationsPage } from '@/pages/notifications/NotificationsPage';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import * as notificationsApi from '@/api/notifications';

vi.mock('@/api/notifications');
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

describe('NotificationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderPage = () => {
    return render(
      <MemoryRouter initialEntries={['/notifications']}>
        <AuthProvider>
          <Routes>
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/candidate/applications" element={<div data-testid="applications-page">Applications Page</div>} />
            <Route path="*" element={<div>Not Found</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );
  };

  const mockNotifications = [
    {
      id: '1',
      title: 'Test Notification 1',
      content: 'Content 1',
      notification_type: 'new_application',
      entity_type: 'application',
      entity_id: 'app-1',
      is_read: false,
      created_at: new Date().toISOString(),
    },
    {
      id: '2',
      title: 'Test Notification 2',
      content: 'Content 2',
      notification_type: 'interview_scheduled',
      entity_type: 'interview',
      entity_id: 'int-1',
      is_read: true,
      created_at: new Date(Date.now() - 86400000).toISOString(),
    },
  ];

  it('renders notification list when authenticated', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getNotifications).mockResolvedValue(mockNotifications);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Thông báo')).toBeInTheDocument();
      expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
      expect(screen.getByText('Test Notification 2')).toBeInTheDocument();
    });
  });

  it('shows empty state when no notifications', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getNotifications).mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Chưa có thông báo')).toBeInTheDocument();
    });
  });

  it('shows error state on failure', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getNotifications).mockRejectedValue(new Error('Network error'));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Không thể tải danh sách thông báo/i)).toBeInTheDocument();
    });
  });

  it('shows unread badge for unread notifications', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getNotifications).mockResolvedValue(mockNotifications);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
    });
  });

  it('marks notification as read on click', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getNotifications).mockResolvedValue(mockNotifications);
    vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
      ...mockNotifications[0],
      is_read: true,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
    });

    await screen.getByText('Test Notification 1').click();

    await waitFor(() => {
      expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('1');
    });
  });

  it('marks all notifications as read', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getNotifications).mockResolvedValue(mockNotifications);
    vi.mocked(notificationsApi.markAllNotificationsRead).mockResolvedValue({
      marked_read: 1,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /đánh dấu tất cả đã đọc/i })).toBeInTheDocument();
    });

    await screen.getByRole('button', { name: /đánh dấu tất cả đã đọc/i }).click();

    await waitFor(() => {
      expect(vi.mocked(notificationsApi.markAllNotificationsRead)).toHaveBeenCalled();
    });
  });

  it('handles unknown entity_type gracefully', async () => {
    const notificationsWithUnknownType = [
      {
        ...mockNotifications[0],
        entity_type: 'unknown_type',
        entity_id: 'unknown-1',
      },
    ];

    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getNotifications).mockResolvedValue(notificationsWithUnknownType);
    vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
      ...notificationsWithUnknownType[0],
      is_read: true,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
    });

    await screen.getByText('Test Notification 1').click();

    await waitFor(() => {
      expect(screen.getByText('Thông báo')).toBeInTheDocument();
    });
  });

  it('shows unread count in header', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(notificationsApi.getNotifications).mockResolvedValue(mockNotifications);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/bạn có 1 thông báo chưa đọc/i)).toBeInTheDocument();
    });
  });
});