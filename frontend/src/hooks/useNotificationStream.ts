import { useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getUnreadNotificationCount, getStreamTicket } from '@/api/notifications';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';

export function useNotificationStream() {
  const { isAuthenticated } = useAuth();
  const { setUnreadCount } = useUnreadCountStore();

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const isConnectingRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const isResyncingRef = useRef(false);
  const resyncPendingRef = useRef(false);
  const resyncGenerationRef = useRef(0);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Handlers for read invalidation events from NotificationsPage
  const handleReadRef = useRef<() => void>();
  const handleReadAllRef = useRef<() => void>();

  // Listen for read invalidation events from NotificationsPage
  useEffect(() => {
    const handleRead = () => {
      if (isMountedRef.current) {
        resyncUnreadCount();
      }
    };

    const handleReadAll = () => {
      if (isMountedRef.current) {
        resyncUnreadCount();
      }
    };

    handleReadRef.current = handleRead;
    handleReadAllRef.current = handleReadAll;

    window.addEventListener('notification:read', handleRead);
    window.addEventListener('notification:read-all', handleReadAll);

    return () => {
      window.removeEventListener('notification:read', handleRead);
      window.removeEventListener('notification:read-all', handleReadAll);
    };
  }, []);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const response = await getUnreadNotificationCount();
      return response.unread_count;
    } catch (error) {
      console.warn('Failed to fetch unread count:', error);
      return -1; // -1 indicates failure
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

  // Resync function with single-flight + pending invalidation pattern
  const resyncUnreadCount = useCallback(async () => {
    if (!isMountedRef.current) return;

    const currentGeneration = ++resyncGenerationRef.current;

    // If already resyncing, mark pending and return
    if (isResyncingRef.current) {
      resyncPendingRef.current = true;
      return;
    }

    isResyncingRef.current = true;

    try {
      const count = await fetchUnreadCount();

      // Check if component is still mounted and generation hasn't changed
      if (!isMountedRef.current || resyncGenerationRef.current !== currentGeneration) {
        return;
      }

      // Only update if count is valid (not -1 which indicates failure)
      if (count >= 0) {
        setUnreadCount(count);
      }
    } catch (error) {
      console.warn('Resync unread count failed:', error);
      // Don't update state on failure - keep current value
    } finally {
      isResyncingRef.current = false;

      // If there was a pending invalidation, run another resync
      if (resyncPendingRef.current) {
        resyncPendingRef.current = false;
        // Use setTimeout to allow current call stack to complete
        setTimeout(() => resyncUnreadCount(), 0);
      }
    }
  }, [fetchUnreadCount, setUnreadCount]);

  // Debounced resync for notification.created events
  const triggerResync = useCallback(() => {
    if (!isMountedRef.current) return;

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null;
      resyncUnreadCount();
    }, 300);
  }, []);

  const fetchUnreadCountInitial = useCallback(async () => {
    try {
      const response = await getUnreadNotificationCount();
      return response.unread_count;
    } catch (error) {
      console.warn('Failed to fetch unread count:', error);
      return 0;
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

        // Trigger resync on successful reconnect
        if (isMountedRef.current) {
          resyncUnreadCount();
        }
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

          // Trigger resync instead of increment
          triggerResync();

          // Still dispatch custom event for UI components that need it
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

          // Clean up debounce timer
          if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current);
            debounceTimerRef.current = null;
          }

          scheduleReconnect();
        }
      };
    } catch (error) {
      console.error('[NotificationStream] Failed to connect:', error);
      isConnectingRef.current = false;
      scheduleReconnect();
    }
  }, [fetchTicket, resyncUnreadCount, triggerResync]);

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
  }, [connect]);

  const disconnect = useCallback(() => {
    isMountedRef.current = false;

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    // Remove event listeners
    if (handleReadRef.current) {
      window.removeEventListener('notification:read', handleReadRef.current);
    }
    if (handleReadAllRef.current) {
      window.removeEventListener('notification:read-all', handleReadAllRef.current);
    }

    isConnectingRef.current = false;
    reconnectAttemptsRef.current = 0;
    isResyncingRef.current = false;
    resyncPendingRef.current = false;
  }, []);

  useEffect(() => {
    const fetchInitialCount = async () => {
      const count = await fetchUnreadCountInitial();
      return count;
    };
    fetchInitialCount().then(setUnreadCount);
  }, [fetchUnreadCountInitial, setUnreadCount]);

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
  }, [isAuthenticated, connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
  }, []);

  return {
    isConnected: false,
  };
}