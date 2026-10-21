import { useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getUnreadNotificationCount, getStreamTicket } from '@/api/notifications';
import { clearToken, dispatchLogoutEvent } from '@/api/client';
import { formatLockNotice, storeLockNotice } from '@/utils/lockNotice';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';

// Server-sent named event for admin subscription invalidations.
export const ADMIN_SUBSCRIPTION_CHANGED_EVENT = 'admin.subscription.changed';
// Server-sent named event for admin email-outbox status transitions.
export const EMAIL_OUTBOX_UPDATED_EVENT = 'email.outbox.updated';
// Server-sent named event emitted on the locked user's private channel when an
// admin locks the account that is currently in use.
export const ACCOUNT_LOCKED_EVENT = 'account.locked';
// Server-sent invalidation events for recruiter and candidate pipeline views.
export const PIPELINE_UPDATED_EVENT = 'pipeline.updated';
export const CANDIDATE_PIPELINE_UPDATED_EVENT = 'candidate.pipeline.updated';
// DOM events rebroadcast by this hook for interested UI components.
export const ADMIN_SUBSCRIPTION_CHANGED_DOM_EVENT = 'admin:subscription:changed';
export const ADMIN_EMAIL_OUTBOX_UPDATED_DOM_EVENT = 'admin:email_outbox:updated';
export const PIPELINE_UPDATED_DOM_EVENT = 'pipeline:updated';
export const CANDIDATE_PIPELINE_UPDATED_DOM_EVENT = 'candidate:pipeline:updated';
export const STREAM_CONNECTED_DOM_EVENT = 'stream:connected';
// DOM event rebroadcast when a subscription-related notification reaches the
// current user (activation, plan change or revocation), so subscription views
// can silently invalidate their cached state without a manual reload. The
// detail is an invalidation signal only - never authoritative entitlement data.
export const USER_SUBSCRIPTION_CHANGED_DOM_EVENT = 'subscription:changed';

const SUBSCRIPTION_ENTITY_TYPE = 'subscription';
const SUBSCRIPTION_NOTIFICATION_TYPE_PREFIX = 'subscription_';

export interface AdminSubscriptionChangedDetail {
  user_id?: string;
  subscription_id?: string | null;
  action?: string;
  timestamp?: string;
}

export interface AdminEmailOutboxUpdatedDetail {
  message_id?: string | null;
  status?: string;
  action?: string;
  attempts?: number | null;
  max_attempts?: number | null;
  next_attempt_at?: string | null;
  sent_at?: string | null;
  has_error?: boolean;
  timestamp?: string;
}

export interface AccountLockedDetail {
  user_id?: string;
  reason?: string | null;
  locked_at?: string | null;
}

export interface SubscriptionNotificationDetail {
  notification_type?: string;
  entity_type?: string | null;
  entity_id?: string | null;
}

export interface PipelineUpdatedDetail {
  company_id?: string;
  job_id?: string;
  application_id?: string;
  action?: string;
  from_status?: string | null;
  to_status?: string | null;
  timestamp?: string;
}

export interface CandidatePipelineUpdatedDetail {
  job_id?: string;
  application_id?: string;
  action?: string;
  from_status?: string | null;
  to_status?: string | null;
  timestamp?: string;
}

function parsePipelineDetail<T>(raw: string): T | null {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null;
    }
    return parsed as T;
  } catch {
    return null;
  }
}

function isSubscriptionNotification(
  data: unknown,
): data is SubscriptionNotificationDetail {
  if (!data || typeof data !== 'object') return false;
  const candidate = data as SubscriptionNotificationDetail;
  if (candidate.entity_type === SUBSCRIPTION_ENTITY_TYPE) return true;
  return (
    typeof candidate.notification_type === 'string' &&
    candidate.notification_type.startsWith(SUBSCRIPTION_NOTIFICATION_TYPE_PREFIX)
  );
}

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
          // Notify listeners (e.g. admin subscription list) that the stream is
          // live again so they can silently catch up on missed changes.
          window.dispatchEvent(new CustomEvent(STREAM_CONNECTED_DOM_EVENT));
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

          // Bridge subscription notifications so subscription views (e.g. the
          // Plans page) invalidate their state without a manual reload.
          if (isSubscriptionNotification(data)) {
            window.dispatchEvent(
              new CustomEvent(USER_SUBSCRIPTION_CHANGED_DOM_EVENT, { detail: data })
            );
          }
        } catch (error) {
          console.warn('Failed to process notification:', error);
        }
      });

      eventSource.addEventListener(ADMIN_SUBSCRIPTION_CHANGED_EVENT, (event) => {
        try {
          const data = JSON.parse(event.data) as AdminSubscriptionChangedDetail;
          window.dispatchEvent(
            new CustomEvent(ADMIN_SUBSCRIPTION_CHANGED_DOM_EVENT, { detail: data })
          );
        } catch (error) {
          console.warn('Failed to process admin subscription event:', error);
        }
      });

      eventSource.addEventListener(EMAIL_OUTBOX_UPDATED_EVENT, (event) => {
        try {
          const data = JSON.parse(event.data) as AdminEmailOutboxUpdatedDetail;
          window.dispatchEvent(
            new CustomEvent(ADMIN_EMAIL_OUTBOX_UPDATED_DOM_EVENT, { detail: data })
          );
        } catch (error) {
          console.warn('Failed to process admin email outbox event:', error);
        }
      });

      eventSource.addEventListener(PIPELINE_UPDATED_EVENT, (event) => {
        const data = parsePipelineDetail<PipelineUpdatedDetail>(event.data);
        if (!data) {
          console.warn('Failed to process pipeline invalidation');
          return;
        }
        window.dispatchEvent(
          new CustomEvent(PIPELINE_UPDATED_DOM_EVENT, { detail: data })
        );
      });

      eventSource.addEventListener(CANDIDATE_PIPELINE_UPDATED_EVENT, (event) => {
        const data = parsePipelineDetail<CandidatePipelineUpdatedDetail>(
          event.data
        );
        if (!data) {
          console.warn('Failed to process candidate pipeline invalidation');
          return;
        }
        window.dispatchEvent(
          new CustomEvent(CANDIDATE_PIPELINE_UPDATED_DOM_EVENT, { detail: data })
        );
      });

      eventSource.addEventListener(ACCOUNT_LOCKED_EVENT, (event) => {
        // The named event itself is authoritative for eviction: even a malformed
        // payload must never leave a locked user signed in.
        let reason: string | null = null;
        try {
          const data = JSON.parse(event.data) as AccountLockedDetail;
          reason = data?.reason ?? null;
        } catch (error) {
          console.warn('Failed to parse account lock event:', error);
        }

        // Persist a one-time notice, then evict immediately through the existing
        // local logout mechanism. Never await the server logout here: a slow or
        // failing request must not delay forced eviction.
        storeLockNotice(formatLockNotice(reason));
        clearToken();
        dispatchLogoutEvent();
      });

eventSource.onerror = (error) => {
        console.warn('[NotificationStream] Connection error:', error);

        // Always close the EventSource to prevent native browser reconnect with stale ticket
        // This is critical because the ticket is single-use - native retry would reuse the stale ticket
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }

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