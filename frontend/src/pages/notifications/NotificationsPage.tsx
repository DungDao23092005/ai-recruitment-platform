import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import {
  Calendar,
  Check,
  ChevronRight,
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
import { getNotifications, markNotificationRead, markAllNotificationsRead } from '@/api/notifications';
import type { Notification } from '@/types/notification';

const ITEMS_PER_PAGE = 20;

const ENTITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  application: MessageSquare,
  interview: Calendar,
};

const ENTITY_LABELS: Record<string, string> = {
  application: 'Đơn ứng tuyển',
  interview: 'Phỏng vấn',
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

function getEntityRoute(entityType: string | null, entityId: string | null): string | null {
  if (!entityType || !entityId) return null;

  switch (entityType) {
    case 'application':
      return `/candidate/applications`;
    case 'interview':
      return `/candidate/applications`;
    default:
      return null;
  }
}

export function NotificationsPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const navigate = useNavigate();

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [totalUnread, setTotalUnread] = useState(0);

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

      // Calculate total unread from first page only (or we could fetch unread count separately)
      if (pageNum === 1) {
        const unreadCount = newNotifications.filter((n) => !n.is_read).length;
        setTotalUnread(unreadCount);
      }
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
    if (notification.is_read) return;
    try {
      await markNotificationRead(notification.id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n))
      );
      setTotalUnread((prev) => Math.max(0, prev - 1));

      // Navigate to entity route
      const route = getEntityRoute(notification.entity_type, notification.entity_id);
      if (route) {
        navigate(route);
      }
    } catch {
      setError('Không thể đánh dấu đã đọc. Vui lòng thử lại.');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setTotalUnread(0);
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
        description={`Bạn có ${totalUnread} thông báo chưa đọc`}
        actions={
          totalUnread > 0 ? (
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

      {loading ? (
        <div className="space-y-4">
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
}

function NotificationCard({ notification, onClick }: NotificationCardProps) {
  const EntityIcon = notification.entity_type
    ? ENTITY_ICONS[notification.entity_type] || MessageSquare
    : MessageSquare;
  const entityLabel = notification.entity_type
    ? ENTITY_LABELS[notification.entity_type] || 'Đối tượng'
    : 'Đối tượng';

  const hasEntityRoute = !!getEntityRoute(notification.entity_type, notification.entity_id);

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

          {hasEntityRoute && (
            <div className="flex items-center justify-center text-muted-foreground">
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function getBadgeVariant(type: string): 'success' | 'warning' | 'info' | 'destructive' | 'neutral' {
  switch (type) {
    case 'application_status_changed':
    case 'interview_scheduled':
    case 'interview_confirmed':
      return 'success';
    case 'interview_updated':
    case 'new_application':
      return 'info';
    case 'interview_cancelled':
    case 'application_withdrawn':
    case 'interview_declined':
      return 'warning';
    default:
      return 'neutral';
  }
}

function formatNotificationType(type: string): string {
  const typeMap: Record<string, string> = {
    application_status_changed: 'Cập nhật trạng thái',
    interview_scheduled: 'Lịch phỏng vấn mới',
    interview_updated: 'Cập nhật phỏng vấn',
    interview_cancelled: 'Hủy phỏng vấn',
    new_application: 'Đơn mới',
    application_withdrawn: 'Rút đơn',
    interview_confirmed: 'Xác nhận phỏng vấn',
    interview_declined: 'Từ chối phỏng vấn',
  };
  return typeMap[type] || type;
}