import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import {
  Calendar,
  Check,
  ChevronRight,
  CreditCard,
  Loader2,
  Mail,
  MessageSquare,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { ErrorBanner } from '@/components/ui/error-banner';
import { PageHeader } from '@/components/common/PageHeader';
import { useAuth } from '@/contexts/AuthContext';
import { useOptionalWorkspace } from '@/contexts/WorkspaceContext';
import { getNotifications, markNotificationRead, markAllNotificationsRead } from '@/api/notifications';
import { getApplicationDetail } from '@/api/applications';
import { getInterview } from '@/api/interviews';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';
import type { Notification } from '@/types/notification';
import type { UserRole } from '@/types/auth';

const ITEMS_PER_PAGE = 20;

const ENTITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  application: MessageSquare,
  interview: Calendar,
  subscription: CreditCard,
};

const ENTITY_LABELS: Record<string, string> = {
  application: 'Đơn ứng tuyển',
  interview: 'Phỏng vấn',
  subscription: 'Gói dịch vụ',
  candidate_quota: 'Hạn mức AI',
  user: 'Tài khoản',
};

function NotificationSkeleton() {
  return (
    <Card className="w-full">
      <CardContent className="p-4">
        <div className="flex gap-3">
          <Skeleton className="h-10 w-10 rounded-lg" />
          <div className="flex-1 space-y-3">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function getEntityRoute(entityType: string | null, entityId: string | null, userRole: UserRole): string | null {
  if (!entityType) return null;

  switch (entityType) {
    case 'application':
      if (!entityId || userRole === 'recruiter' || userRole === 'admin') {
        return null;
      }
      return `/candidate/applications?id=${encodeURIComponent(entityId)}`;
    case 'interview':
      if (userRole === 'recruiter' || userRole === 'admin') {
        return null;
      }
      return `/candidate/interviews`;
    case 'subscription':
      return `/plans`;
    default:
      return null;
  }
}

export function isNotificationNavigable(
  notification: Notification,
  userRole?: UserRole,
  workspaceRole?: string | null
): boolean {
  // All candidate_quota notifications are non-navigable for every role
  if (notification.entity_type === 'candidate_quota') {
    return false;
  }

  // user / account_unlocked notifications are non-navigable
  if (notification.entity_type === 'user' || notification.notification_type === 'account_unlocked') {
    return false;
  }

  // Active workspace interviewer
  if (workspaceRole === 'interviewer') {
    return notification.entity_type === 'interview';
  }

  // Recruiter and Platform Admin
  if (userRole === 'recruiter' || userRole === 'admin') {
    if (notification.entity_type === 'application' || notification.entity_type === 'interview') {
      return Boolean(notification.entity_id);
    }
    if (notification.entity_type === 'subscription') {
      return true;
    }
    return false;
  }

  // Candidate (or default role)
  if (notification.entity_type === 'application') {
    return Boolean(notification.entity_id);
  }
  if (notification.entity_type === 'interview') {
    return true;
  }
  if (notification.entity_type === 'subscription') {
    return true;
  }

  return false;
}

export function NotificationsPage() {
  const { isAuthenticated, isLoading: authLoading, currentUser } = useAuth();
  const workspace = useOptionalWorkspace();
  const navigate = useNavigate();
  const { unreadCount, decrement, increment, setUnreadCount } = useUnreadCountStore();

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const isWorkspaceLoading = currentUser?.role === 'recruiter' && Boolean(workspace?.isLoading);

  const fetchNotifications = async (pageNum: number = 1, append = false) => {
    try {
      setError(null);
      if (!append) setLoading(true);
      const newNotifications = await getNotifications({ skip: (pageNum - 1) * ITEMS_PER_PAGE, limit: ITEMS_PER_PAGE });
      if (append) {
        setNotifications((prev) => [...prev, ...newNotifications]);
      } else {
        setNotifications(newNotifications);
      }
      setHasMore(newNotifications.length === ITEMS_PER_PAGE);
      setPage(pageNum);
    } catch (err) {
      setError('Không thể tải danh sách thông báo. Vui lòng thử lại.');
    } finally {
      setLoading(false);
    }
  };

  const loadMore = () => {
    if (!loading && hasMore) {
      fetchNotifications(page + 1, true);
    }
  };

  const retry = () => fetchNotifications(1, false);

  const handleMarkRead = async (notification: Notification) => {
    if (currentUser?.role === 'recruiter' && workspace?.isLoading) {
      return;
    }

    // Separate read handling from navigation
    const userRole = currentUser?.role;
    const workspaceRole = workspace?.selectedWorkspace?.role;

    // Helper to resolve and navigate
    const resolveAndNavigate = async () => {
      if (!isNotificationNavigable(notification, userRole, workspaceRole)) {
        return;
      }

      if (
        workspaceRole === 'interviewer' &&
        notification.entity_type === 'interview'
      ) {
        navigate('/interviewer/interviews');
        return;
      }

      if (notification.entity_type === 'application' && notification.entity_id && userRole === 'recruiter') {
        try {
          const application = await getApplicationDetail(notification.entity_id);
          if (application.job_id) {
            navigate(`/recruiter/jobs/${application.job_id}/applicants`);
          } else {
            navigate(`/recruiter/jobs`);
          }
        } catch {
          navigate(`/recruiter/jobs`);
        }
      } else if (notification.entity_type === 'interview' && notification.entity_id && userRole === 'recruiter') {
        try {
          const interview = await getInterview(notification.entity_id);
          if (interview.application_id) {
            const application = await getApplicationDetail(interview.application_id);
            if (application.job_id) {
              navigate(`/recruiter/jobs/${application.job_id}/applicants`);
            } else {
              navigate(`/recruiter/jobs`);
            }
          } else {
            navigate(`/recruiter/jobs`);
          }
        } catch {
          navigate(`/recruiter/jobs`);
        }
      } else if (notification.entity_type === 'application' && notification.entity_id && userRole === 'admin') {
        try {
          const application = await getApplicationDetail(notification.entity_id);
          if (application.job_id) {
            navigate(`/admin/jobs/${application.job_id}/applicants`);
          } else {
            navigate(`/admin/jobs`);
          }
        } catch {
          navigate(`/admin/jobs`);
        }
      } else if (notification.entity_type === 'interview' && notification.entity_id && userRole === 'admin') {
        try {
          const interview = await getInterview(notification.entity_id);
          if (interview.application_id) {
            const application = await getApplicationDetail(interview.application_id);
            if (application.job_id) {
              navigate(`/admin/jobs/${application.job_id}/applicants`);
            } else {
              navigate(`/admin/jobs`);
            }
          } else {
            navigate(`/admin/jobs`);
          }
        } catch {
          navigate(`/admin/jobs`);
        }
      } else {
        const route = getEntityRoute(notification.entity_type, notification.entity_id, userRole || 'candidate');
        if (route) {
          navigate(route);
        }
      }
    };

    // If already read, just navigate without mark-read
    if (notification.is_read) {
      await resolveAndNavigate();
      return;
    }

    // Unread notification: optimistic update + fire-and-forget mark-read + navigate
    setNotifications((prev) =>
      prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n))
    );
    decrement();

    // Fire-and-forget mark-read API
    markNotificationRead(notification.id)
      .then(() => {
        // Success - dispatch event for authoritative resync
        window.dispatchEvent(new CustomEvent('notification:read'));
      })
      .catch(() => {
        // Rollback on failure
        setNotifications((prev) =>
          prev.map((n) => (n.id === notification.id ? { ...n, is_read: false } : n))
        );
        increment();
      });

    // Always navigate regardless of mark-read status
    await resolveAndNavigate();
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
      // Dispatch event for authoritative resync
      window.dispatchEvent(new CustomEvent('notification:read-all'));
    } catch {
      setError('Không thể đánh dấu tất cả đã đọc. Vui lòng thử lại.');
    }
  };

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      navigate('/login');
      return;
    }
    if (isAuthenticated) {
      fetchNotifications(1, false);
    }
  }, [isAuthenticated, authLoading]);

  if (authLoading) {
    return (
      <div className="container py-6 sm:py-8">
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <NotificationSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="container py-6 sm:py-8">
      <PageHeader
        title="Thông báo"
        description={`Bạn có ${unreadCount} thông báo chưa đọc`}
        actions={
          unreadCount > 0 && !isWorkspaceLoading ? (
            <Button variant="outline" size="sm" onClick={handleMarkAllRead}>
              <Check className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
              Đánh dấu tất cả đã đọc
            </Button>
          ) : null
        }
      />

      {error && (
        <ErrorBanner message={error} onRetry={retry} className="mb-6" />
      )}

      {loading || isWorkspaceLoading ? (
        <div className="space-y-4" data-testid="notifications-skeleton">
          {[...Array(5)].map((_, i) => (
            <NotificationSkeleton key={i} />
          ))}
        </div>
      ) : notifications.length === 0 ? (
        <EmptyState
          icon={<Mail className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có thông báo"
          description="Thông báo mới sẽ xuất hiện ở đây khi bạn nhận được cập nhật về đơn ứng tuyển, phỏng vấn, hoặc các hoạt động khác."
        />
      ) : (
        <>
          <div className="space-y-3" role="list" aria-label="Danh sách thông báo">
            {notifications.map((notification) => (
              <NotificationCard
                key={notification.id}
                notification={notification}
                onClick={() => handleMarkRead(notification)}
                isNavigable={isNotificationNavigable(
                  notification,
                  currentUser?.role,
                  workspace?.selectedWorkspace?.role
                )}
              />
            ))}
          </div>

          {hasMore && (
            <div className="mt-6 text-center">
              <Button variant="outline" onClick={loadMore} disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    Đang tải thêm...
                  </>
                ) : (
                  'Tải thêm thông báo'
                )}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface NotificationCardProps {
  notification: Notification;
  onClick: () => void;
  isNavigable?: boolean;
}

function NotificationCard({ notification, onClick, isNavigable = false }: NotificationCardProps) {
  const EntityIcon = notification.entity_type
    ? ENTITY_ICONS[notification.entity_type] || MessageSquare
    : MessageSquare;
  const entityLabel = notification.entity_type
    ? ENTITY_LABELS[notification.entity_type] || 'Đối tượng'
    : 'Đối tượng';

  return (
    <Card
      className={cn(
        'w-full cursor-pointer transition-all hover:shadow-md',
        !notification.is_read && 'bg-primary/5 border-primary/20 ring-1 ring-primary/20',
        notification.is_read && 'bg-card'
      )}
      onClick={onClick}
      role="listitem"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <CardContent className="p-4">
        <div className="flex gap-3">
          <div
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
              !notification.is_read ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
            )}
          >
            <EntityIcon className="h-5 w-5" aria-hidden="true" />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <h3 className={cn('font-medium text-foreground', !notification.is_read && 'font-semibold')}>
                {notification.title}
              </h3>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {formatDate(notification.created_at)}
              </span>
            </div>

            <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
              {notification.content}
            </p>

            <div className="mt-2 flex items-center gap-2">
              <Badge variant="outline-ai" className="text-xs">
                {entityLabel}
              </Badge>
              <Badge variant={getBadgeVariant(notification.notification_type)} className="text-xs">
                {formatNotificationType(notification.notification_type)}
              </Badge>
              {!notification.is_read && (
                <span className="flex h-2 w-2 rounded-full bg-primary" aria-label="Chưa đọc" />
              )}
            </div>
          </div>

          {isNavigable && (
            <div
              className="flex items-center justify-center text-muted-foreground"
              data-testid="notification-chevron"
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function getBadgeVariant(type: string): 'success' | 'warning' | 'info' | 'destructive' | 'neutral' {
  switch (type) {
    case 'application_status_changed':
    case 'interview_scheduled':
    case 'interview_confirmed':
    case 'subscription_activated':
    case 'application_submitted':
    case 'offer_accepted':
    case 'account_unlocked':
      return 'success';

    case 'interview_updated':
    case 'new_application':
    case 'subscription_plan_changed':
    case 'interview_assigned':
    case 'evaluation_submitted':
      return 'info';

    case 'interview_cancelled':
    case 'application_withdrawn':
    case 'interview_declined':
    case 'subscription_revoked':
    case 'offer_declined':
    case 'interview_unassigned':
    case 'company_returned_to_free':
    case 'candidate_paid_quota_exhausted':
    case 'candidate_free_quota_exhausted':
    case 'candidate_returned_to_free':
      return 'warning';

    default:
      return 'neutral';
  }
}

export function formatNotificationType(type: string): string {
  const typeMap: Record<string, string> = {
    application_status_changed: 'Cập nhật trạng thái',
    interview_scheduled: 'Lịch phỏng vấn mới',
    interview_updated: 'Cập nhật phỏng vấn',
    interview_cancelled: 'Hủy phỏng vấn',
    new_application: 'Đơn mới',
    application_withdrawn: 'Rút đơn',
    interview_confirmed: 'Xác nhận phỏng vấn',
    interview_declined: 'Từ chối phỏng vấn',
    subscription_activated: 'Kích hoạt gói',
    subscription_plan_changed: 'Đổi gói dịch vụ',
    subscription_revoked: 'Thu hồi gói dịch vụ',
    application_submitted: 'Nộp đơn thành công',
    offer_accepted: 'Chấp nhận lời mời',
    offer_declined: 'Từ chối lời mời',
    interview_assigned: 'Phân công phỏng vấn',
    interview_unassigned: 'Hủy phân công',
    evaluation_submitted: 'Đánh giá phỏng vấn',
    company_returned_to_free: 'Hết hạn gói dịch vụ',
    candidate_paid_quota_exhausted: 'Hết hạn mức trả phí',
    candidate_free_quota_exhausted: 'Hết hạn mức miễn phí',
    candidate_returned_to_free: 'Quay lại gói miễn phí',
    account_unlocked: 'Mở khóa tài khoản',
  };
  return typeMap[type] || type;
}
