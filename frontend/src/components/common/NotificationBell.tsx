import { useNavigate } from 'react-router-dom';
import { cn } from '@/utils/cn';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';
import { useNotificationStream } from '@/hooks/useNotificationStream';
import { Bell } from 'lucide-react';

export function NotificationBell() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const { unreadCount } = useUnreadCountStore();

  // Initialize the notification stream
  useNotificationStream();

  const handleClick = () => {
    // Navigate to notifications page
    navigate('/notifications');
  };

  if (!isAuthenticated) {
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
      {unreadCount > 0 && (
        <span
          className="absolute -top-1 -right-1 h-5 min-w-5 rounded-full bg-destructive px-1.5 text-[10px] font-medium text-white flex items-center justify-center"
        >
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
      <Bell className="h-5 w-5" aria-hidden="true" />
    </Button>
  );
}
