import { useEffect, useRef, useState } from 'react';
import { Bell, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/utils/cn';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { getUnreadNotificationCount } from '@/api/notifications';

export function NotificationBell() {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);
  const [isFetching, setIsFetching] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMountedRef = useRef(true);

  const fetchUnreadCount = async () => {
    if (!isAuthenticated || isFetching) return;
    setIsFetching(true);
    try {
      const response = await getUnreadNotificationCount();
      if (isMountedRef.current) {
        setUnreadCount(response.unread_count);
      }
    } catch {
      // Silently fail - don't break the UI
    } finally {
      if (isMountedRef.current) {
        setIsFetching(false);
      }
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    if (isAuthenticated) {
      fetchUnreadCount();
      intervalRef.current = setInterval(fetchUnreadCount, 150000); // 2.5 minutes
    }
    return () => {
      isMountedRef.current = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isAuthenticated]);

  const handleClick = () => {
    navigate('/notifications');
  };

  if (isLoading || !isAuthenticated) {
    return null;
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={handleClick}
      className={cn('relative', unreadCount > 0 && 'text-primary')}
      aria-label={`Thông báo${unreadCount > 0 ? `, ${unreadCount} chưa đọc` : ''}`}
    >
      {isFetching ? (
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      ) : (
        <Bell className="h-5 w-5" aria-hidden="true" />
      )}
      {unreadCount > 0 && (
        <Badge
          variant="destructive"
          className="absolute -top-1 -right-1 h-5 min-w-5 rounded-full px-1.5 text-[10px] font-medium"
        >
          {unreadCount > 99 ? '99+' : unreadCount}
        </Badge>
      )}
    </Button>
  );
}