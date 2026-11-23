/// <reference types="vitest/globals" />
import { render, screen, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotificationsPage } from '@/pages/notifications/NotificationsPage';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { useOptionalWorkspace } from '@/contexts/WorkspaceContext';
import * as notificationsApi from '@/api/notifications';
import * as applicationsApi from '@/api/applications';
import * as interviewsApi from '@/api/interviews';
import * as workspacesApi from '@/api/workspaces';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';

vi.mock('@/api/notifications');
vi.mock('@/api/applications');
vi.mock('@/api/interviews');
vi.mock('@/api/workspaces');
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('@/contexts/WorkspaceContext', () => ({
  useOptionalWorkspace: vi.fn(),
  useWorkspace: vi.fn(),
  WorkspaceProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('@/stores/useUnreadCountStore', () => ({
  useUnreadCountStore: vi.fn(),
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
    vi.mocked(workspacesApi.getMyInvitations).mockResolvedValue([]);
    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 0,
      decrement: vi.fn(),
      increment: vi.fn(),
      setUnreadCount: vi.fn(),
    });
    vi.mocked(useOptionalWorkspace).mockReturnValue({
      workspaces: [],
      selectedWorkspace: null,
      isLoading: false,
      error: null,
      selectWorkspace: vi.fn(),
      refreshWorkspaces: vi.fn(),
    });
  });

  const renderPage = (initialEntries = ['/notifications']) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>
          <Routes>
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/candidate/applications" element={<div data-testid="candidate-applications-page">Candidate Applications Page</div>} />
            <Route path="/candidate/interviews" element={<div data-testid="candidate-interviews-page">Candidate Interviews Page</div>} />
            <Route path="/recruiter/jobs/:jobId/applicants" element={<div data-testid="recruiter-applicants-page">Recruiter Applicants Page</div>} />
            <Route path="/recruiter/jobs" element={<div data-testid="recruiter-jobs-page">Recruiter Jobs Page</div>} />
            <Route path="/admin/jobs/:jobId/applicants" element={<div data-testid="admin-job-applicants-page">Admin Job Applicants Page</div>} />
            <Route path="/admin/jobs" element={<div data-testid="admin-jobs-page">Admin Jobs Page</div>} />
            <Route path="/interviewer/interviews" element={<div data-testid="interviewer-interviews-page">Interviewer Interviews Page</div>} />
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
    vi.mocked(workspacesApi.getMyInvitations).mockResolvedValue([]);
    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 0,
      decrement: vi.fn(),
      increment: vi.fn(),
      setUnreadCount: vi.fn(),
    });
    vi.mocked(useOptionalWorkspace).mockReturnValue({
      workspaces: [],
      selectedWorkspace: null,
      isLoading: false,
      error: null,
      selectWorkspace: vi.fn(),
      refreshWorkspaces: vi.fn(),
    });
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

    // Mock store with unreadCount > 0 so button is visible
    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 1,
      decrement: vi.fn(),
      setUnreadCount: vi.fn(),
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

    // Mock store with unreadCount = 1
    vi.mocked(useUnreadCountStore).mockReturnValue({
      unreadCount: 1,
      decrement: vi.fn(),
      setUnreadCount: vi.fn(),
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

      // Should navigate to the targeted candidate application
      expect(mockNavigate).toHaveBeenCalledWith('/candidate/applications?id=app-1');
    });

    it('Candidate: application notification without entity id does not navigate', async () => {
      vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
        { ...mockNotifications[0], id: '1', entity_type: 'application', entity_id: null, is_read: false },
      ]);
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

      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('Candidate: interview notification navigates to /candidate/interviews', async () => {
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

      // Should navigate to candidate interviews
      expect(mockNavigate).toHaveBeenCalledWith('/candidate/interviews');
      expect(mockNavigate).not.toHaveBeenCalledWith('/candidate/applications');
    });

    // ===== PHASE 1: ALREADY-READ NAVIGATION =====

    it('already-read notification still navigates without calling mark-read', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('candidate')
      );

      const alreadyReadNotifications = [
        { ...mockNotifications[0], id: '1', entity_type: 'application', entity_id: 'app-1', is_read: true },
      ];

      vi.mocked(notificationsApi.getNotifications).mockResolvedValue(alreadyReadNotifications);

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
      });

      // Click the already-read notification
      await screen.getByText('Test Notification 1').click();

      // Should NOT call markNotificationRead for already-read notification
      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).not.toHaveBeenCalled();
      });

      // Should NOT call decrement or increment
      const decrementMock = vi.mocked(useUnreadCountStore).mock.results[0].value.decrement;
      const incrementMock = vi.mocked(useUnreadCountStore).mock.results[0].value.increment;
      expect(decrementMock).not.toHaveBeenCalled();
      expect(incrementMock).not.toHaveBeenCalled();

      // Should still navigate to the targeted candidate application
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/candidate/applications?id=app-1');
      });
    });

    // ===== PHASE 1: MARK-READ FAILURE / ROLLBACK =====

    it('mark-read failure triggers rollback and still navigates', async () => {
      vi.mocked(useAuth).mockReturnValue(
        mockUser('candidate')
      );

      const unreadNotifications = [
        { ...mockNotifications[0], id: '1', entity_type: 'application', entity_id: 'app-1', is_read: false },
      ];

      // Mock markNotificationRead to reject
      vi.mocked(notificationsApi.getNotifications).mockResolvedValue(unreadNotifications);
      vi.mocked(notificationsApi.markNotificationRead).mockRejectedValue(new Error('Network error'));

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Test Notification 1')).toBeInTheDocument();
      });

      // Click the unread notification
      await screen.getByText('Test Notification 1').click();

      // Verify markNotificationRead was called
      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('1');
      });

      // Verify decrement was called once
      const decrementMock = vi.mocked(useUnreadCountStore).mock.results[0].value.decrement;
      await waitFor(() => {
        expect(decrementMock).toHaveBeenCalledTimes(1);
      });

      // Navigation should still happen despite mark-read failure
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/candidate/applications?id=app-1');
      });

      // Wait for the promise rejection to be handled (rollback)
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 0));
      });

      // Verify increment was called once for rollback
      const incrementMock = vi.mocked(useUnreadCountStore).mock.results[0].value.increment;
      expect(incrementMock).toHaveBeenCalledTimes(1);
    });
  });

  describe('Subscription activation notifications', () => {
    const subscriptionNotification = {
      id: 'sub-1',
      title: 'Kích hoạt gói dịch vụ thành công',
      content: 'Gói "Professional" đã được kích hoạt thành công. Thời hạn sử dụng đến 31/12/2026.',
      notification_type: 'subscription_activated',
      entity_type: 'subscription',
      entity_id: '22222222-2222-2222-2222-222222222222',
      is_read: false,
      created_at: new Date().toISOString(),
    };

    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
      vi.mocked(notificationsApi.getNotifications).mockResolvedValue([subscriptionNotification]);
      vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
        ...subscriptionNotification,
        is_read: true,
      });
    });

    it('renders the subscription icon, entity label and activation badge', async () => {
      const { container } = renderPage();

      await waitFor(() => {
        expect(screen.getByText('Kích hoạt gói dịch vụ thành công')).toBeInTheDocument();
      });

      // Entity label
      expect(screen.getByText('Gói dịch vụ')).toBeInTheDocument();
      // Notification-type badge
      expect(screen.getByText('Kích hoạt gói')).toBeInTheDocument();
      // CreditCard icon from lucide-react
      expect(container.querySelector('svg.lucide-credit-card')).not.toBeNull();
    });

    it('navigates to /plans when clicked', async () => {
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Kích hoạt gói dịch vụ thành công')).toBeInTheDocument();
      });

      await screen.getByText('Kích hoạt gói dịch vụ thành công').click();

      await waitFor(() => {
        expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('sub-1');
      });

      expect(mockNavigate).toHaveBeenCalledWith('/plans');
    });
  });

  describe('Interviewer workspace-role-aware notification navigation (NOTIF-01)', () => {
    const mockWorkspace = (role: 'admin' | 'recruiter' | 'interviewer' | null, isLoading = false) => ({
      workspaces: role
        ? [
            {
              id: 'ws-1',
              company_id: 'comp-1',
              company_name: 'Acme Corp',
              role,
              is_active: true,
            },
          ]
        : [],
      selectedWorkspace: role
        ? {
            id: 'ws-1',
            company_id: 'comp-1',
            company_name: 'Acme Corp',
            role,
            is_active: true,
          }
        : null,
      isLoading,
      error: null,
      selectWorkspace: vi.fn(),
      refreshWorkspaces: vi.fn(),
    });

    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
      vi.mocked(useOptionalWorkspace).mockReturnValue(mockWorkspace('interviewer'));
      vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
        id: 'int-notif-1',
        title: 'Interview Notification',
        content: 'Interview notification details',
        notification_type: 'interview_assigned',
        entity_type: 'interview',
        entity_id: 'interview-123',
        is_read: true,
        created_at: new Date().toISOString(),
      });
      vi.mocked(applicationsApi.getApplicationDetail).mockResolvedValue({
        id: 'app-1',
        job_id: 'test-job-id',
        title: 'Test Job',
        company: { name: 'Test Company' },
        status: 'published',
      });
      vi.mocked(interviewsApi.getInterview).mockResolvedValue({
        id: 'interview-123',
        application_id: 'app-1',
        scheduled_at: new Date().toISOString(),
        duration_minutes: 60,
        interview_type: 'technical',
        status: 'scheduled',
      });
    });

    describe('A. All 4 Interview Notification Types with interviewer workspace role', () => {
      const interviewNotificationTypes = [
        'interview_assigned',
        'interview_unassigned',
        'interview_updated',
        'interview_cancelled',
      ] as const;

      interviewNotificationTypes.forEach((notifType) => {
        it(`navigates to /interviewer/interviews for ${notifType} without calling recruiter APIs`, async () => {
          vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
            {
              id: `notif-${notifType}`,
              title: `Interview ${notifType}`,
              content: `Details for ${notifType}`,
              notification_type: notifType,
              entity_type: 'interview',
              entity_id: 'interview-123',
              is_read: false,
              created_at: new Date().toISOString(),
            },
          ]);

          renderPage();

          await waitFor(() => {
            expect(screen.getByText(`Interview ${notifType}`)).toBeInTheDocument();
          });

          await screen.getByText(`Interview ${notifType}`).click();

          await waitFor(() => {
            expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith(`notif-${notifType}`);
          });

          expect(mockNavigate).toHaveBeenCalledWith('/interviewer/interviews');
          expect(interviewsApi.getInterview).not.toHaveBeenCalled();
          expect(applicationsApi.getApplicationDetail).not.toHaveBeenCalled();
          expect(mockNavigate).not.toHaveBeenCalledWith('/recruiter/jobs');
          expect(mockNavigate).not.toHaveBeenCalledWith(expect.stringContaining('/recruiter/jobs/'));
        });
      });
    });

    describe('B. Already-Read Interview Notification', () => {
      it('navigates directly to /interviewer/interviews without calling mark-read or recruiter APIs', async () => {
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'read-interview-notif',
            title: 'Already Read Interview',
            content: 'Interview has already been read',
            notification_type: 'interview_assigned',
            entity_type: 'interview',
            entity_id: 'interview-123',
            is_read: true,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByText('Already Read Interview')).toBeInTheDocument();
        });

        await screen.getByText('Already Read Interview').click();

        expect(mockNavigate).toHaveBeenCalledWith('/interviewer/interviews');
        expect(notificationsApi.markNotificationRead).not.toHaveBeenCalled();
        expect(interviewsApi.getInterview).not.toHaveBeenCalled();
        expect(applicationsApi.getApplicationDetail).not.toHaveBeenCalled();
      });
    });

    describe('C. Workspace Loading Guard', () => {
      it('renders skeleton UI, suppresses mark-all-read action, and does not expose clickable cards while workspace is loading', async () => {
        vi.mocked(useOptionalWorkspace).mockReturnValue(mockWorkspace(null, true));
        vi.mocked(useUnreadCountStore).mockReturnValue({
          unreadCount: 3,
          decrement: vi.fn(),
          increment: vi.fn(),
          setUnreadCount: vi.fn(),
        });
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'loading-notif-1',
            title: 'Pending Workspace Notification',
            content: 'Should not be clickable yet',
            notification_type: 'interview_assigned',
            entity_type: 'interview',
            entity_id: 'interview-123',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByTestId('notifications-skeleton')).toBeInTheDocument();
        });

        // Cards must not be rendered while workspace is loading
        expect(screen.queryByText('Pending Workspace Notification')).not.toBeInTheDocument();

        // Mark all as read button must be suppressed
        expect(screen.queryByText('Đánh dấu tất cả đã đọc')).not.toBeInTheDocument();

        // Recruiter APIs must not be called
        expect(interviewsApi.getInterview).not.toHaveBeenCalled();
        expect(applicationsApi.getApplicationDetail).not.toHaveBeenCalled();
      });
    });

    describe('D. Recruiter Invariance', () => {
      it('preserves existing recruiter interview navigation when active workspace role is recruiter', async () => {
        vi.mocked(useOptionalWorkspace).mockReturnValue(mockWorkspace('recruiter'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'recruiter-interview-notif',
            title: 'Recruiter Interview Update',
            content: 'Recruiter should see applicants page',
            notification_type: 'interview_assigned',
            entity_type: 'interview',
            entity_id: 'interview-123',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByText('Recruiter Interview Update')).toBeInTheDocument();
        });

        await screen.getByText('Recruiter Interview Update').click();

        await waitFor(() => {
          expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('recruiter-interview-notif');
        });

        expect(interviewsApi.getInterview).toHaveBeenCalledWith('interview-123');
        expect(applicationsApi.getApplicationDetail).toHaveBeenCalledWith('app-1');
        expect(mockNavigate).toHaveBeenCalledWith('/recruiter/jobs/test-job-id/applicants');
        expect(mockNavigate).not.toHaveBeenCalledWith('/interviewer/interviews');
      });
    });

    describe('E. Unresolved Workspace', () => {
      it('does not throw, does not infer interviewer from notification type, and preserves recruiter fallback', async () => {
        // Workspace loaded but no workspace is selected (unresolved)
        vi.mocked(useOptionalWorkspace).mockReturnValue(mockWorkspace(null, false));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'unresolved-ws-interview-notif',
            title: 'Unresolved Workspace Interview',
            content: 'Notice type is interview_assigned but workspace is null',
            notification_type: 'interview_assigned',
            entity_type: 'interview',
            entity_id: 'interview-123',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByText('Unresolved Workspace Interview')).toBeInTheDocument();
        });

        // Clicking the notification card should not throw
        await screen.getByText('Unresolved Workspace Interview').click();

        await waitFor(() => {
          expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('unresolved-ws-interview-notif');
        });

        // Must NOT infer interviewer role from notification_type="interview_assigned"
        // Must preserve existing recruiter navigation
        expect(interviewsApi.getInterview).toHaveBeenCalledWith('interview-123');
        expect(applicationsApi.getApplicationDetail).toHaveBeenCalledWith('app-1');
        expect(mockNavigate).toHaveBeenCalledWith('/recruiter/jobs/test-job-id/applicants');
        expect(mockNavigate).not.toHaveBeenCalledWith('/interviewer/interviews');
      });
    });
  });

  describe('Notification Navigation & Localization (Task 3)', () => {
    describe('A. Candidate Interview Navigation', () => {
      it('navigates to /candidate/interviews and not /candidate/applications for unread interview notification', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'cand-int-nav-1',
            title: 'Interview Scheduled',
            content: 'Your interview is scheduled',
            notification_type: 'interview_scheduled',
            entity_type: 'interview',
            entity_id: 'int-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);
        vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
          id: 'cand-int-nav-1',
          title: 'Interview Scheduled',
          content: 'Your interview is scheduled',
          notification_type: 'interview_scheduled',
          entity_type: 'interview',
          entity_id: 'int-1',
          is_read: true,
          created_at: new Date().toISOString(),
        });

        renderPage();

        await waitFor(() => {
          expect(screen.getByText('Interview Scheduled')).toBeInTheDocument();
        });

        await screen.getByText('Interview Scheduled').click();

        await waitFor(() => {
          expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('cand-int-nav-1');
        });

        expect(mockNavigate).toHaveBeenCalledWith('/candidate/interviews');
        expect(mockNavigate).not.toHaveBeenCalledWith('/candidate/applications');
      });

      it('navigates to /candidate/interviews for already-read interview notification without calling markNotificationRead', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'cand-int-read-1',
            title: 'Already Read Interview',
            content: 'Your interview is scheduled',
            notification_type: 'interview_scheduled',
            entity_type: 'interview',
            entity_id: 'int-1',
            is_read: true,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByText('Already Read Interview')).toBeInTheDocument();
        });

        await screen.getByText('Already Read Interview').click();

        expect(vi.mocked(notificationsApi.markNotificationRead)).not.toHaveBeenCalled();
        expect(mockNavigate).toHaveBeenCalledWith('/candidate/interviews');
        expect(mockNavigate).not.toHaveBeenCalledWith('/candidate/applications');
      });
    });

    describe('B. All 11 Localized Notification Types', () => {
      const localizedTypes = [
        { type: 'application_submitted', label: 'Nộp đơn thành công', variantClass: 'text-success' },
        { type: 'offer_accepted', label: 'Chấp nhận lời mời', variantClass: 'text-success' },
        { type: 'offer_declined', label: 'Từ chối lời mời', variantClass: 'text-warning' },
        { type: 'interview_assigned', label: 'Phân công phỏng vấn', variantClass: 'text-info' },
        { type: 'interview_unassigned', label: 'Hủy phân công', variantClass: 'text-warning' },
        { type: 'evaluation_submitted', label: 'Đánh giá phỏng vấn', variantClass: 'text-info' },
        { type: 'company_returned_to_free', label: 'Hết hạn gói dịch vụ', variantClass: 'text-warning' },
        { type: 'candidate_paid_quota_exhausted', label: 'Hết hạn mức trả phí', variantClass: 'text-warning' },
        { type: 'candidate_free_quota_exhausted', label: 'Hết hạn mức miễn phí', variantClass: 'text-warning' },
        { type: 'candidate_returned_to_free', label: 'Quay lại gói miễn phí', variantClass: 'text-warning' },
        { type: 'account_unlocked', label: 'Mở khóa tài khoản', variantClass: 'text-success' },
      ] as const;

      localizedTypes.forEach(({ type, label, variantClass }) => {
        it(`renders correct Vietnamese label and badge variant for ${type}`, async () => {
          vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
          vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
            {
              id: `notif-${type}`,
              title: `Notification Title for ${type}`,
              content: `Content for ${type}`,
              notification_type: type,
              entity_type: 'application',
              entity_id: 'app-1',
              is_read: false,
              created_at: new Date().toISOString(),
            },
          ]);

          renderPage();

          await waitFor(() => {
            expect(screen.getByText(`Notification Title for ${type}`)).toBeInTheDocument();
          });

          // Verify Vietnamese label is rendered
          const badgeElement = screen.getByText(label);
          expect(badgeElement).toBeInTheDocument();

          // Verify badge class contains expected variant style
          expect(badgeElement.className).toContain(variantClass);

          // Verify raw snake_case identifier is NOT displayed
          expect(screen.queryByText(type)).not.toBeInTheDocument();
        });
      });
    });

    describe('C. Entity Label Mapping', () => {
      it('renders "Hạn mức AI" for candidate_quota entity type', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'quota-notif',
            title: 'Hết hạn mức',
            content: 'Bạn đã dùng hết lượt',
            notification_type: 'candidate_free_quota_exhausted',
            entity_type: 'candidate_quota',
            entity_id: 'quota-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByText('Hết hạn mức')).toBeInTheDocument();
        });

        expect(screen.getByText('Hạn mức AI')).toBeInTheDocument();
      });

      it('renders "Tài khoản" for user entity type', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'user-notif',
            title: 'Tài khoản đã mở khóa',
            content: 'Chào mừng trở lại',
            notification_type: 'account_unlocked',
            entity_type: 'user',
            entity_id: 'user-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByText('Tài khoản đã mở khóa')).toBeInTheDocument();
        });

        expect(screen.getByText('Tài khoản')).toBeInTheDocument();
      });

      it('renders "Thành viên công ty" for company_membership entity type', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'member-notif',
            title: 'Thành viên mới tham gia công ty',
            content: 'dev@example.com đã tham gia TechNova AI với vai trò Nhà tuyển dụng.',
            notification_type: 'company_member_joined',
            entity_type: 'company_membership',
            entity_id: 'membership-uuid-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByText('Thành viên mới tham gia công ty')).toBeInTheDocument();
        });

        expect(screen.getByText('Thành viên công ty')).toBeInTheDocument();
      });
    });

    describe('D. Candidate Chevron Visibility', () => {
      it('shows chevron for candidate application notification with entity ID', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'cand-app-notif',
            title: 'Application Update',
            content: 'Status changed',
            notification_type: 'application_status_changed',
            entity_type: 'application',
            entity_id: 'app-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        const { container } = renderPage();
        await waitFor(() => {
          expect(screen.getByText('Application Update')).toBeInTheDocument();
        });
        expect(screen.getByTestId('notification-chevron')).toBeInTheDocument();
        expect(container.querySelector('svg.lucide-chevron-right')).not.toBeNull();
      });

      it('shows chevron for candidate interview notification', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'cand-int-notif',
            title: 'Interview Invite',
            content: 'Interview details',
            notification_type: 'interview_scheduled',
            entity_type: 'interview',
            entity_id: 'int-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        const { container } = renderPage();
        await waitFor(() => {
          expect(screen.getByText('Interview Invite')).toBeInTheDocument();
        });
        expect(screen.getByTestId('notification-chevron')).toBeInTheDocument();
        expect(container.querySelector('svg.lucide-chevron-right')).not.toBeNull();
      });

      it('shows chevron for candidate subscription notification', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'cand-sub-notif',
            title: 'Subscription Active',
            content: 'Plan active',
            notification_type: 'subscription_activated',
            entity_type: 'subscription',
            entity_id: 'sub-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        const { container } = renderPage();
        await waitFor(() => {
          expect(screen.getByText('Subscription Active')).toBeInTheDocument();
        });
        expect(screen.getByTestId('notification-chevron')).toBeInTheDocument();
        expect(container.querySelector('svg.lucide-chevron-right')).not.toBeNull();
      });

      it('hides chevron for quota notification', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'quota-chevron-notif',
            title: 'Quota Warning',
            content: 'Quota exhausted',
            notification_type: 'candidate_paid_quota_exhausted',
            entity_type: 'candidate_quota',
            entity_id: 'quota-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        const { container } = renderPage();
        await waitFor(() => {
          expect(screen.getByText('Quota Warning')).toBeInTheDocument();
        });
        expect(screen.queryByTestId('notification-chevron')).not.toBeInTheDocument();
        expect(container.querySelector('svg.lucide-chevron-right')).toBeNull();
      });

      it('hides chevron for account unlock notification', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'unlock-chevron-notif',
            title: 'Account Unlocked',
            content: 'Unlocked',
            notification_type: 'account_unlocked',
            entity_type: 'user',
            entity_id: 'user-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        const { container } = renderPage();
        await waitFor(() => {
          expect(screen.getByText('Account Unlocked')).toBeInTheDocument();
        });
        expect(screen.queryByTestId('notification-chevron')).not.toBeInTheDocument();
        expect(container.querySelector('svg.lucide-chevron-right')).toBeNull();
      });
    });

    describe('E. Interviewer Chevron Visibility', () => {
      it('shows chevron for interview notification when active workspace role is interviewer', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(useOptionalWorkspace).mockReturnValue({
          workspaces: [{ id: 'ws-1', company_id: 'c1', company_name: 'Co', role: 'interviewer', is_active: true }],
          selectedWorkspace: { id: 'ws-1', company_id: 'c1', company_name: 'Co', role: 'interviewer', is_active: true },
          isLoading: false,
          error: null,
          selectWorkspace: vi.fn(),
          refreshWorkspaces: vi.fn(),
        } as any);

        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'int-ws-notif',
            title: 'Assigned Interview',
            content: 'Interview assignment',
            notification_type: 'interview_assigned',
            entity_type: 'interview',
            entity_id: 'int-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        const { container } = renderPage();
        await waitFor(() => {
          expect(screen.getByText('Assigned Interview')).toBeInTheDocument();
        });
        expect(screen.getByTestId('notification-chevron')).toBeInTheDocument();
        expect(container.querySelector('svg.lucide-chevron-right')).not.toBeNull();
      });

      it('hides chevron for non-interview notification when active workspace role is interviewer', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(useOptionalWorkspace).mockReturnValue({
          workspaces: [{ id: 'ws-1', company_id: 'c1', company_name: 'Co', role: 'interviewer', is_active: true }],
          selectedWorkspace: { id: 'ws-1', company_id: 'c1', company_name: 'Co', role: 'interviewer', is_active: true },
          isLoading: false,
          error: null,
          selectWorkspace: vi.fn(),
          refreshWorkspaces: vi.fn(),
        } as any);

        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'app-ws-notif',
            title: 'Application Notif for Interviewer',
            content: 'Interviewer has no application route',
            notification_type: 'new_application',
            entity_type: 'application',
            entity_id: 'app-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        const { container } = renderPage();
        await waitFor(() => {
          expect(screen.getByText('Application Notif for Interviewer')).toBeInTheDocument();
        });
        expect(screen.queryByTestId('notification-chevron')).not.toBeInTheDocument();
        expect(container.querySelector('svg.lucide-chevron-right')).toBeNull();
      });
    });

    describe('F. Recruiter & Admin Chevron Visibility', () => {
      it('shows chevron for recruiter application notification with valid entity ID', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'rec-app-notif',
            title: 'Recruiter App',
            content: 'New applicant',
            notification_type: 'new_application',
            entity_type: 'application',
            entity_id: 'app-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();
        await waitFor(() => {
          expect(screen.getByText('Recruiter App')).toBeInTheDocument();
        });
        expect(screen.getByTestId('notification-chevron')).toBeInTheDocument();
      });

      it('shows chevron for recruiter interview notification with valid entity ID', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'rec-int-notif',
            title: 'Recruiter Interview',
            content: 'Scheduled',
            notification_type: 'interview_scheduled',
            entity_type: 'interview',
            entity_id: 'int-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();
        await waitFor(() => {
          expect(screen.getByText('Recruiter Interview')).toBeInTheDocument();
        });
        expect(screen.getByTestId('notification-chevron')).toBeInTheDocument();
      });

      it('hides chevron for recruiter interview notification when entity ID is missing', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'rec-no-id-notif',
            title: 'Recruiter Interview No ID',
            content: 'No entity ID',
            notification_type: 'interview_scheduled',
            entity_type: 'interview',
            entity_id: null,
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();
        await waitFor(() => {
          expect(screen.getByText('Recruiter Interview No ID')).toBeInTheDocument();
        });
        expect(screen.queryByTestId('notification-chevron')).not.toBeInTheDocument();
      });

      it('shows chevron for platform admin interview notification with valid entity ID', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('admin'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'admin-int-notif',
            title: 'Admin Interview',
            content: 'Scheduled',
            notification_type: 'interview_scheduled',
            entity_type: 'interview',
            entity_id: 'int-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();
        await waitFor(() => {
          expect(screen.getByText('Admin Interview')).toBeInTheDocument();
        });
        expect(screen.getByTestId('notification-chevron')).toBeInTheDocument();
      });

      it('hides chevron for recruiter/admin with quota or account unlock notification', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
          {
            id: 'rec-quota-notif',
            title: 'Quota Warning',
            content: 'Quota exhausted',
            notification_type: 'candidate_paid_quota_exhausted',
            entity_type: 'candidate_quota',
            entity_id: 'quota-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
          {
            id: 'rec-unlock-notif',
            title: 'Account Unlocked',
            content: 'Unlocked',
            notification_type: 'account_unlocked',
            entity_type: 'user',
            entity_id: 'user-1',
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);

        renderPage();
        await waitFor(() => {
          expect(screen.getByText('Quota Warning')).toBeInTheDocument();
          expect(screen.getByText('Account Unlocked')).toBeInTheDocument();
        });
        expect(screen.queryAllByTestId('notification-chevron')).toHaveLength(0);
      });
    });

    describe('G. Quota Click Behavior', () => {
      const quotaTypes = [
        'candidate_paid_quota_exhausted',
        'candidate_free_quota_exhausted',
        'candidate_returned_to_free',
      ] as const;

      quotaTypes.forEach((quotaType) => {
        it(`clicking ${quotaType} does not navigate and preserves mark-as-read`, async () => {
          vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
          vi.mocked(notificationsApi.getNotifications).mockResolvedValue([
            {
              id: `notif-${quotaType}`,
              title: `Quota Title for ${quotaType}`,
              content: `Content for ${quotaType}`,
              notification_type: quotaType,
              entity_type: 'candidate_quota',
              entity_id: 'quota-1',
              is_read: false,
              created_at: new Date().toISOString(),
            },
          ]);
          vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
            id: `notif-${quotaType}`,
            title: `Quota Title for ${quotaType}`,
            content: `Content for ${quotaType}`,
            notification_type: quotaType,
            entity_type: 'candidate_quota',
            entity_id: 'quota-1',
            is_read: true,
            created_at: new Date().toISOString(),
          });

          renderPage();

          await waitFor(() => {
            expect(screen.getByText(`Quota Title for ${quotaType}`)).toBeInTheDocument();
          });

          await screen.getByText(`Quota Title for ${quotaType}`).click();

          // Mark as read was called
          await waitFor(() => {
            expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith(`notif-${quotaType}`);
          });

          // Must NOT navigate anywhere
          expect(mockNavigate).not.toHaveBeenCalled();
          expect(mockNavigate).not.toHaveBeenCalledWith('/plans');
          expect(mockNavigate).not.toHaveBeenCalledWith('/candidate/portal');
        });
      });
    });

    describe('H. Company Invitation Notifications and In-App Pending Invitations', () => {
      it('displays company invitation notification and navigates to /invitations/accept on click', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        const notif = {
          id: 'notif-inv-1',
          title: 'Lời mời tham gia công ty',
          content: 'Bạn nhận được lời mời tham gia TechNova AI với vai trò Nhà tuyển dụng.',
          notification_type: 'company_invitation',
          entity_type: 'company_invitation',
          entity_id: 'inv-uuid-123',
          is_read: false,
          created_at: new Date().toISOString(),
        };
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([notif]);
        vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
          ...notif,
          is_read: true,
        });

        renderPage();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Lời mời tham gia công ty' })).toBeInTheDocument();
          expect(
            screen.getByText('Bạn nhận được lời mời tham gia TechNova AI với vai trò Nhà tuyển dụng.'),
          ).toBeInTheDocument();
        });

        // Chevron is present indicating navigable
        expect(screen.getAllByTestId('notification-chevron').length).toBeGreaterThan(0);

        // Click notification
        await screen.getByRole('heading', { name: 'Lời mời tham gia công ty' }).click();

        await waitFor(() => {
          expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('notif-inv-1');
          expect(mockNavigate).toHaveBeenCalledWith('/invitations/accept', {
            state: { invitationId: 'inv-uuid-123' },
          });
        });
      });

      it('displays pending in-app invitations card and navigates to respond', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([]);
        vi.mocked(workspacesApi.getMyInvitations).mockResolvedValue([
          {
            id: 'inv-uuid-999',
            company_id: 'company-uuid-1',
            company_name: 'TechNova AI',
            company_slug: 'technova-ai',
            role: 'recruiter',
            status: 'pending',
            expires_at: new Date(Date.now() + 86400000).toISOString(),
            created_at: new Date().toISOString(),
            can_accept: true,
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(
            screen.getByRole('heading', { name: /TechNova AI/ }),
          ).toBeInTheDocument();
          expect(screen.getByText(/Nhà tuyển dụng/)).toBeInTheDocument();
        });

        const respondBtn = screen.getByRole('button', { name: 'Xem và phản hồi' });
        expect(respondBtn).toBeInTheDocument();
        respondBtn.click();

        expect(mockNavigate).toHaveBeenCalledWith('/invitations/accept', {
          state: { invitationId: 'inv-uuid-999' },
        });
      });

      it('refreshes pending invitations and notifications when invitation:revoked event is received', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([]);
        vi.mocked(workspacesApi.getMyInvitations).mockResolvedValueOnce([
          {
            id: 'inv-uuid-888',
            company_id: 'company-uuid-1',
            company_name: 'TechNova AI',
            company_slug: 'technova-ai',
            role: 'interviewer',
            status: 'pending',
            expires_at: new Date(Date.now() + 86400000).toISOString(),
            created_at: new Date().toISOString(),
            can_accept: true,
          },
        ]);

        renderPage();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: /TechNova AI/ })).toBeInTheDocument();
        });

        // Next response after revocation: no pending invitations
        vi.mocked(workspacesApi.getMyInvitations).mockResolvedValueOnce([]);

        await act(async () => {
          window.dispatchEvent(
            new CustomEvent('invitation:revoked', {
              detail: { invitation_id: 'inv-uuid-888', company_id: 'company-uuid-1' },
            }),
          );
        });

        await waitFor(() => {
          expect(screen.queryByRole('heading', { name: /TechNova AI/ })).not.toBeInTheDocument();
        });

        expect(workspacesApi.getMyInvitations).toHaveBeenCalledTimes(2);
      });
    });

    describe('I. Company Membership Notifications', () => {
      const membershipNotif = {
        id: 'notif-member-1',
        title: 'Thành viên mới tham gia công ty',
        content: 'newuser@example.com đã tham gia TechNova AI với vai trò Nhà tuyển dụng.',
        notification_type: 'company_member_joined',
        entity_type: 'company_membership',
        entity_id: 'membership-uuid-123',
        is_read: false,
        created_at: new Date().toISOString(),
      };

      it('displays company membership notification with Users icon and navigates to /recruiter/workspace for company admin', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(useOptionalWorkspace).mockReturnValue({
          workspaces: [],
          selectedWorkspace: {
            company_id: 'c1',
            company_name: 'TechNova AI',
            company_slug: 'technova-ai',
            role: 'admin',
            is_platform_admin: false,
          } as any,
          isLoading: false,
          error: null,
          selectWorkspace: vi.fn(),
          refreshWorkspaces: vi.fn(),
        });
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([membershipNotif]);
        vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
          ...membershipNotif,
          is_read: true,
        });

        renderPage();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Thành viên mới tham gia công ty' })).toBeInTheDocument();
          expect(screen.getByText(membershipNotif.content)).toBeInTheDocument();
        });

        // Chevron is present for company admin
        expect(screen.getAllByTestId('notification-chevron').length).toBeGreaterThan(0);

        // Click notification
        await screen.getByRole('heading', { name: 'Thành viên mới tham gia công ty' }).click();

        await waitFor(() => {
          expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('notif-member-1');
          expect(mockNavigate).toHaveBeenCalledWith('/recruiter/workspace');
        });
      });

      it('navigates to /recruiter/workspace for workspace recruiter', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(useOptionalWorkspace).mockReturnValue({
          workspaces: [],
          selectedWorkspace: {
            company_id: 'c1',
            company_name: 'TechNova AI',
            company_slug: 'technova-ai',
            role: 'recruiter',
            is_platform_admin: false,
          } as any,
          isLoading: false,
          error: null,
          selectWorkspace: vi.fn(),
          refreshWorkspaces: vi.fn(),
        });
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([membershipNotif]);
        vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
          ...membershipNotif,
          is_read: true,
        });

        renderPage();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Thành viên mới tham gia công ty' })).toBeInTheDocument();
        });

        // Chevron is present for recruiter
        expect(screen.getAllByTestId('notification-chevron').length).toBeGreaterThan(0);

        await screen.getByRole('heading', { name: 'Thành viên mới tham gia công ty' }).click();

        await waitFor(() => {
          expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('notif-member-1');
          expect(mockNavigate).toHaveBeenCalledWith('/recruiter/workspace');
        });
      });

      it('is non-navigable for candidate: hides chevron and clicking marks read without navigating', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('candidate'));
        vi.mocked(useOptionalWorkspace).mockReturnValue({
          workspaces: [],
          selectedWorkspace: null,
          isLoading: false,
          error: null,
          selectWorkspace: vi.fn(),
          refreshWorkspaces: vi.fn(),
        });
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([membershipNotif]);
        vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
          ...membershipNotif,
          is_read: true,
        });

        renderPage();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Thành viên mới tham gia công ty' })).toBeInTheDocument();
        });

        // Chevron is hidden for candidate
        expect(screen.queryAllByTestId('notification-chevron')).toHaveLength(0);

        await screen.getByRole('heading', { name: 'Thành viên mới tham gia công ty' }).click();

        await waitFor(() => {
          expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('notif-member-1');
        });
        expect(mockNavigate).not.toHaveBeenCalled();
      });

      it('is non-navigable for interviewer: hides chevron and clicking marks read without navigating', async () => {
        vi.mocked(useAuth).mockReturnValue(mockUser('recruiter'));
        vi.mocked(useOptionalWorkspace).mockReturnValue({
          workspaces: [],
          selectedWorkspace: {
            company_id: 'c1',
            company_name: 'TechNova AI',
            company_slug: 'technova-ai',
            role: 'interviewer',
            is_platform_admin: false,
          } as any,
          isLoading: false,
          error: null,
          selectWorkspace: vi.fn(),
          refreshWorkspaces: vi.fn(),
        });
        vi.mocked(notificationsApi.getNotifications).mockResolvedValue([membershipNotif]);
        vi.mocked(notificationsApi.markNotificationRead).mockResolvedValue({
          ...membershipNotif,
          is_read: true,
        });

        renderPage();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Thành viên mới tham gia công ty' })).toBeInTheDocument();
        });

        // Chevron is hidden for interviewer
        expect(screen.queryAllByTestId('notification-chevron')).toHaveLength(0);

        await screen.getByRole('heading', { name: 'Thành viên mới tham gia công ty' }).click();

        await waitFor(() => {
          expect(vi.mocked(notificationsApi.markNotificationRead)).toHaveBeenCalledWith('notif-member-1');
        });
        expect(mockNavigate).not.toHaveBeenCalled();
      });
    });
  });
});
