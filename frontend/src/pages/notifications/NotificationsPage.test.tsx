/// <reference types="vitest/globals" />
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotificationsPage } from '@/pages/notifications/NotificationsPage';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import * as notificationsApi from '@/api/notifications';
import * as applicationsApi from '@/api/applications';
import * as interviewsApi from '@/api/interviews';

vi.mock('@/api/notifications');
vi.mock('@/api/applications');
vi.mock('@/api/interviews');
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const { mockNavigate } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    MemoryRouter: (await vi.importActual('react-router-dom')).MemoryRouter,
    Routes: (await vi.importActual('react-router-dom')).Routes,
    Route: (await vi.importActual('react-router-dom')).Route,
  };
});

describe('NotificationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
  });

  const renderPage = (initialEntries = ['/notifications']) => {
    return render(
      <MemoryRouter initialEntries={['/notifications']}>
        <AuthProvider>
          <Routes>
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/candidate/applications" element={<div data-testid="candidate-applications-page">Candidate Applications Page</div>} />
            <Route path="/recruiter/jobs/:jobId/applicants" element={<div data-testid="recruiter-applicants-page">Recruiter Applicants Page</div>} />
            <Route path="/recruiter/jobs" element={<div data-testid="recruiter-jobs-page">Recruiter Jobs Page</div>} />
            <Route path="/admin/jobs/:jobId/applicants" element={<div data-testid="admin-job-applicants-page">Admin Job Applicants Page</div>} />
            <Route path="/admin/jobs" element={<div data-testid="admin-jobs-page">Admin Jobs Page</div>} />
            <Route path="/candidate/applications" element={<div data-testid="candidate-applications-page">Candidate Applications Page</div>} />
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

  const mockApplication = {
    id: 'app-1',
    job_id: 'test-job-id',
    title: 'Test Job',
    company: { name: 'Test Company' },
    status: 'published',
  };

  const mockInterview = {
    id: 'int-1',
    application_id: 'app-1',
    scheduled_at: new Date().toISOString(),
    duration_minutes: 60,
    interview_type: 'technical',
    status: 'scheduled',
  };

  const mockUser = (role: 'candidate' | 'recruiter' | 'admin') => ({
    isAuthenticated: true,
    isLoading: false,
    currentUser: { id: '1', email: 'test@test.com', role },
    token: 'token',
    login: vi.fn(),
    logout: vi.fn(),
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
  });

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

  describe('Role-based notification routing', () => {
    beforeEach(() => {
      vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
        ...mockNotifications[0],
        is_read: true,
      });
      vi.mocked(applicationsApi.getApplicationDetail).mockResolvedValue({
        id: 'app-1',
        job_id: 'test-job-id',
        title: 'Test Job',
        company: { name: 'Test Company' },
        status: 'published',
      });
      vi.mocked(interviewsApi.getInterview).mockResolvedValue({
        id: 'int-1',
        application_id: 'app-1',
        scheduled_at: new Date().toISOString(),
        duration_minutes: 60,
        interview_type: 'technical',
        status: 'scheduled',
      });
    });

    // ===== RECRUITER TESTS =====

    it('Recruiter: application notification happy path navigates to /recruiter/jobs/test-job-id/applicants', async () => {
      vi.mocked(useAuth).mockReturnValue({
        isAuthenticated: true,
        isLoading: false,
        currentUser: { id: '1', email: 'recruiter@test.com', role: 'recruiter' },
        token: 'token',
        login: vi.fn(),
        logout: vi.fn(),
      });

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[0], id: '1', entity_type: 'application', entity_id: 'app-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 1').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('1');
      });

      // Should navigate to recruiter applicants page
      expect(mockNavigate).toHaveBeenCalledWith('/recruiter/jobs/test-job-id/applicants');
    });

    it('Recruiter: interview notification happy path navigates to /recruiter/jobs/test-job-id/applicants', async () => {
      vi.mocked(useAuth).mockReturnValue({
        isAuthenticated: true,
        isLoading: false,
        currentUser: { id: '1', email: 'recruiter@test.com', role: 'recruiter' },
        token: 'token',
        login: vi.fn(),
        logout: vi.fn(),
      });

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[1], id: '2', entity_type: 'interview', entity_id: 'int-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 2')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 2').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('2');
      });

      // Should navigate to recruiter applicants page via interview -> application -> job
      expect(mockNavigate).toHaveBeenCalledWith('/recruiter/jobs/test-job-id/applicants');
    });

    it('Recruiter: interview notification fetch fails falls back to /recruiter/jobs', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('recruiter')
      );

      // Make getInterview fail
      vi.mocked(interviewsApi.getInterview).mockRejectedValue(new Error('Not found'));

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[1], id: '2', entity_type: 'interview', entity_id: 'int-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 2')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 2').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('2');
      });

      // Should fallback to /recruiter/jobs
      expect(mockNavigate).toHaveBeenCalledWith('/recruiter/jobs');
      expect(mockNavigate).not.toHaveBeenCalledWith('/candidate/applications');
    });

    it('Recruiter: application notification fetch fails falls back to /recruiter/jobs', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('recruiter')
      );

      // Make getApplicationDetail fail
      vi.mocked(applicationsApi.getApplicationDetail).mockRejectedValue(new Error('Not found'));

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[0], id: '1', entity_type: 'application', entity_id: 'app-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 1').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('1');
      });

      // Should fallback to /recruiter/jobs
      expect(mockNavigate).toHaveBeenCalledWith('/recruiter/jobs');
      expect(mockNavigate).not.toHaveBeenCalledWith('/candidate/applications');
    });

    // ===== ADMIN TESTS =====

    it('Admin: application notification navigates to /admin/jobs/test-job-id/applicants', async () => {
      vi.mocked(useAuth).mockReturnValue({
        isAuthenticated: true,
        isLoading: false,
        currentUser: { id: '1', email: 'admin@test.com', role: 'admin' },
        token: 'token',
        login: vi.fn(),
        logout: vi.fn(),
      });

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[0], id: '1', entity_type: 'application', entity_id: 'app-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 1').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('1');
      });

      // Should navigate to admin job applicants page
      expect(mockNavigate).toHaveBeenCalledWith('/admin/jobs/test-job-id/applicants');
    });

    it('Admin: interview notification navigates to /admin/jobs/test-job-id/applicants', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('admin')
      );

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[1], id: '2', entity_type: 'interview', entity_id: 'int-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 2')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 2').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('2');
      });

      // Should navigate to admin job applicants page
      expect(mockNavigate).toHaveBeenCalledWith('/admin/jobs/test-job-id/applicants');
    });

    it('Admin: interview notification fetch fails falls back to /admin/jobs', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('admin')
      );

      // Make getInterview fail
      vi.mocked(interviewsApi.getInterview).mockRejectedValue(new Error('Not found'));

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[1], id: '2', entity_type: 'interview', entity_id: 'int-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 2')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 2').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('2');
      });

      // Should fallback to /admin/jobs
      expect(mockNavigate).toHaveBeenCalledWith('/admin/jobs');
      expect(mockNavigate).not.toHaveBeenCalledWith('/candidate/applications');
    });

    it('Admin: application notification fetch fails falls back to /admin/jobs', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('admin')
      );

      // Make getApplicationDetail fail
      vi.mocked(applicationsApi.getApplicationDetail).mockRejectedValue(new Error('Not found'));

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[0], id: '1', entity_type: 'application', entity_id: 'app-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 1').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('1');
      });

      // Should fallback to /admin/jobs
      expect(mockNavigate).toHaveBeenCalledWith('/admin/jobs');
      expect(mockNavigate).not.toHaveBeenCalledWith('/candidate/applications');
    });

    // ===== CANDIDATE REGRESSION TESTS =====

    it('Candidate: application notification navigates to /candidate/applications', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('candidate')
      );

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[0], id: '1', entity_type: 'application', entity_id: 'app-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 1').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('1');
      });

      // Should navigate to candidate applications
      expect(mockNavigate).toHaveBeenCalledWith('/candidate/applications');
    });

    it('Candidate: interview notification navigates to /candidate/applications', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('candidate')
      );

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[1], id: '2', entity_type: 'interview', entity_id: 'int-1', is_read: false },
      ]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 2')).toBeInTheDocument();
      });

      await screen.getByText('Test Notification 2').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('2');
      });

      // Should navigate to candidate applications
      expect(mockNavigate).toHaveBeenCalledWith('/candidate/applications');
    });
  });
});