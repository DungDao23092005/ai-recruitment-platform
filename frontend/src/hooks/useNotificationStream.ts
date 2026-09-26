import { useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getUnreadNotificationCount, getStreamTicket } from '@/api/notifications';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';

export function useNotificationStream() {
  const { isAuthenticated } = useAuth();
  const { setUnreadCount, increment } = useUnreadCountStore();

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const isConnectingRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const response = await getUnreadNotificationCount();
      return response.unread_count;
    } catch (error) {
      console.warn('Failed to fetch unread count:', error);
      return 0;
    }
  }, []);

  const fetchTicket = useCallback(async (): Promise<string | null> => {
    try {
      const response = await getStreamTicket();
      return response.ticket;
    } catch (error) {
      console.warn('Failed to get stream ticket:', error);
      return null;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!isMountedRef.current || isConnectingRef.current) return;

    // Close existing EventSource if any
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const ticket = await fetchTicket();
    if (!ticket) {
      console.warn('Failed to get stream ticket');
      scheduleReconnect();
      return;
    }

    isConnectingRef.current = true;

    try {
      const eventSource = new EventSource(`/api/v1/notifications/stream?ticket=${encodeURIComponent(ticket)}`);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        console.log('[NotificationStream] Connected');
        reconnectAttemptsRef.current = 0;
        isConnectingRef.current = false;
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'connected') {
            console.log('[NotificationStream] Connected');
          }
        } catch (error) {
          console.warn('Failed to parse connection event:', error);
        }
      };

      eventSource.addEventListener('notification.created', (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[NotificationStream] Notification received:', data);

          increment();

          window.dispatchEvent(new CustomEvent('notification:created', { detail: data }));
        } catch (error) {
          console.warn('Failed to process notification:', error);
        }
      });

      eventSource.onerror = (error) => {
        console.warn('[NotificationStream] Connection error:', error);

        if (eventSource.readyState === EventSource.CLOSED) {
          console.log('[NotificationStream] Connection closed, scheduling reconnect...');
          // Ensure connecting flag is reset so reconnect can proceed
          isConnectingRef.current = false;
          scheduleReconnect();
        }
      };
    } catch (error) {
      console.error('[NotificationStream] Failed to connect:', error);
      isConnectingRef.current = false;
      scheduleReconnect();
    }
  }, []);

const scheduleReconnect = useCallback(() => {
    if (!isMountedRef.current || reconnectAttemptsRef.current >= 10) {
      console.warn('[NotificationStream] Max reconnect attempts reached');
      return;
    }

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }

    const delay = Math.min(
      1000 * Math.pow(2, reconnectAttemptsRef.current),
      30000
    );

    reconnectAttemptsRef.current += 1;
    console.log(`[NotificationStream] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);

    // Use delay variable to satisfy TypeScript
    void delay;

    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
    }, delay);
  }, []);

  const disconnect = useCallback(() => {
    isMountedRef.current = false;

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    isConnectingRef.current = false;
    reconnectAttemptsRef.current = 0;
  }, []);

  useEffect(() => {
    const fetchInitialCount = async () => {
      const count = await fetchUnreadCount();
      return count;
    };
    fetchInitialCount().then(setUnreadCount);
  }, [fetchUnreadCount]);

  // Connect when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      isMountedRef.current = true;
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [isAuthenticated]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  return {
    isConnected: false,
  };
}
