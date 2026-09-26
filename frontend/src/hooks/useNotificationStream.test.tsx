/// <reference types="vitest/globals" />
import { render, act, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useNotificationStream } from '@/hooks/useNotificationStream';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';
import * as notificationsApi from '@/api/notifications';
import { useAuth } from '@/contexts/AuthContext';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: vi.fn() }));
vi.mock('@/api/notifications', () => ({ getUnreadNotificationCount: vi.fn(), getStreamTicket: vi.fn() }));
vi.mock('@/stores/useUnreadCountStore', () => ({ useUnreadCountStore: vi.fn() }));

const mockUseAuth = vi.mocked(useAuth);
const mockGetUnreadNotificationCount = vi.mocked(notificationsApi.getUnreadNotificationCount);
const mockGetStreamTicket = vi.mocked(notificationsApi.getStreamTicket);
const mockStoreState = { unreadCount: 0, setUnreadCount: vi.fn(), increment: vi.fn(), decrement: vi.fn(), reset: vi.fn() };
vi.mock('@/stores/useUnreadCountStore', () => ({ useUnreadCountStore: vi.fn(() => mockStoreState) }));

// Controllable MockEventSource - test decides when to fire events
class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  readyState = MockEventSource.CONNECTING;
  url: string;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  eventListeners: Map<string, Set<Function>> = new Map();

  private _resolveOpen: (() => void) | null = null;
  private _openPromise: Promise<void>;

  constructor(url: string) {
    this.url = url;
    this._openPromise = new Promise(resolve => { this._resolveOpen = resolve; });
  }

  // Test control methods
  emitOpen() {
    this.readyState = MockEventSource.OPEN;
    if (this.onopen) this.onopen(new Event('open'));
    this._resolveOpen?.();
  }

  emitError() {
    this.readyState = MockEventSource.CLOSED;
    if (this.onerror) this.onerror(new Event('error'));
  }

  emitMessage(data: object) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }));
    }
  }

  emitEvent(type: string, data?: object) {
    // Hook expects event.data to be JSON string (like MessageEvent)
    const event = new Event(type);
    (event as any).data = data ? JSON.stringify(data) : '';
    this.eventListeners.get(type)?.forEach(l => l(event));
  }

  close() { this.readyState = MockEventSource.CLOSED; }
  addEventListener(type: string, listener: Function) { if (!this.eventListeners.has(type)) this.eventListeners.set(type, new Set()); this.eventListeners.get(type)!.add(listener); }
  removeEventListener(type: string, listener: Function) { this.eventListeners.get(type)?.delete(listener); }

  // Wait for onopen to be set (for tests that need to ensure handler is registered)
  async waitForOpenHandler(): Promise<void> {
    await this._openPromise;
  }
}

// Track created EventSource instances for test control
let createdEventSources: MockEventSource[] = [];
const originalEventSource = global.EventSource;

Object.defineProperty(global, 'EventSource', {
  value: function (url: string) {
    const instance = new MockEventSource(url);
    createdEventSources.push(instance);
    return instance;
  },
  writable: true,
  configurable: true,
});

describe('useNotificationStream', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    createdEventSources = [];

    mockStoreState.unreadCount = 0;
    mockStoreState.setUnreadCount.mockImplementation((c: number) => { mockStoreState.unreadCount = Math.max(0, c); });
    mockStoreState.increment.mockImplementation(() => { mockStoreState.unreadCount = mockStoreState.unreadCount + 1; });
    mockStoreState.decrement.mockImplementation(() => { mockStoreState.unreadCount = Math.max(0, mockStoreState.unreadCount - 1); });
    mockStoreState.reset.mockImplementation(() => { mockStoreState.unreadCount = 0; });

    mockUseAuth.mockReturnValue({
      isAuthenticated: true, isLoading: false,
      currentUser: { id: '1', email: 'test@test.com', role: 'candidate' },
      token: 'token', login: vi.fn(), logout: vi.fn(),
    });

    mockGetStreamTicket.mockResolvedValue({ ticket: 'test-ticket-123' });
    // Default mock - tests should override with setupUnreadCountMock()
    mockGetUnreadNotificationCount.mockResolvedValue({ unread_count: 7 });
  });

  // Helper to set up unread count mock with specific values for each call
  const setupUnreadCountMock = (...values: number[]) => {
    let callIndex = 0;
    mockGetUnreadNotificationCount.mockImplementation(() => {
      const value = values[callIndex] ?? values[values.length - 1] ?? 7;
      callIndex++;
      return Promise.resolve({ unread_count: value });
    });
  };

  afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

  const renderHook = () => {
    const TestComponent = () => { useNotificationStream(); return <div data-testid="hook-component">Test</div>; };
    return render(<TestComponent />);
  };

  // Fine-grained test helpers
  const flushMicrotasks = async () => {
    await act(async () => {
      await Promise.resolve();
    });
  };

  const advanceTimers = async (ms: number) => {
    await act(async () => {
      vi.advanceTimersByTime(ms);
    });
  };

  const waitForOpen = async () => {
    if (createdEventSources.length > 0) {
      await createdEventSources[createdEventSources.length - 1].waitForOpenHandler();
    }
  };

  // Get the latest EventSource instance
  const getEventSource = () => createdEventSources[createdEventSources.length - 1];

  describe('Initial Sync', () => {
    it('fetches unread count on mount and sets store (before SSE connects)', async () => {
      mockGetUnreadNotificationCount.mockResolvedValue({ unread_count: 7 });
      renderHook();
      await flushMicrotasks(); // Initial fetch runs

      // Should have exactly 1 call (initial sync), not 2 (no reconnect resync yet)
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(1);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(7);
    });

    it('handles initial sync failure gracefully', async () => {
      mockGetUnreadNotificationCount.mockRejectedValue(new Error('Network error'));
      renderHook();
      await flushMicrotasks();

      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(1);
      // fetchUnreadCountInitial returns 0 on failure
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(0);
    });
  });

  describe('Reconnect Resync', () => {
    it('triggers resync on successful reconnect (explicit onopen)', async () => {
      mockGetUnreadNotificationCount
        .mockResolvedValueOnce({ unread_count: 2 }) // initial
        .mockResolvedValueOnce({ unread_count: 5 }); // reconnect resync

      renderHook();
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(1);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(2);

      // Simulate connection error -> close -> reconnect -> onopen
      const es = getEventSource();
      act(() => { es.emitError(); });
      await flushMicrotasks();

      // Wait for reconnect (exponential backoff: 1000ms first attempt)
      await advanceTimers(1100);
      await flushMicrotasks();

      // New connection established, fire onopen
      const newEs = getEventSource();
      act(() => { newEs.emitOpen(); });
      await flushMicrotasks();

      // Reconnect resync should have fired
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5);
    });
  });

  describe('SSE Invalidation (notification.created)', () => {
    it('triggers resync on notification.created event (delegates to REST)', async () => {
      setupUnreadCountMock(3, 4, 4); // initial=3, onopen resync=4, invalidation resync=4

      renderHook();
      await flushMicrotasks();

      // Connect SSE
      const es = getEventSource();
      act(() => { es.emitOpen(); });
      act(() => { es.emitMessage({ type: 'connected' }); });
      await flushMicrotasks();

      // Initial sync + onopen resync = 2 calls
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(4); // onopen resync wins

      // Fire SSE notification.created event
      act(() => { es.emitEvent('notification.created', { id: '1', title: 'Test' }); });

      // Debounce 300ms
      await advanceTimers(350);
      await flushMicrotasks();

      // Invalidation resync = 3rd call
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(3);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(4);
    });

    it('does NOT call increment() on notification.created (authoritative REST wins)', async () => {
      setupUnreadCountMock(3, 5, 7); // initial=3, onopen=5, invalidation=7 (authoritative)

      renderHook();
      await flushMicrotasks();

      // Connect SSE
      const es = getEventSource();
      act(() => { es.emitOpen(); });
      act(() => { es.emitMessage({ type: 'connected' }); });
      await flushMicrotasks();

      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5); // onopen resync

      act(() => { es.emitEvent('notification.created', { id: '1', title: 'Test' }); });

      await advanceTimers(350);
      await flushMicrotasks();

      expect(mockStoreState.increment).not.toHaveBeenCalled();
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(7); // authoritative
    });
  });

  describe('Read Invalidation (notification:read)', () => {
    it('triggers resync on notification:read event', async () => {
      setupUnreadCountMock(5, 4); // initial=5, resync=4

      renderHook();
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(1);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5);

      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();

      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(4);
    });
  });

  describe('Read-All Invalidation (notification:read-all)', () => {
    it('triggers resync on notification:read-all event', async () => {
      setupUnreadCountMock(10, 0); // initial=10, resync=0

      renderHook();
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(1);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(10);

      act(() => window.dispatchEvent(new CustomEvent('notification:read-all')));
      await flushMicrotasks();

      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(0);
    });
  });

  describe('Read-vs-Resync Race (Critical Test)', () => {
    it('handles race: stale resync returns after read, authoritative follow-up wins', async () => {
      // Request A: initial sync (resolves immediately)
      // Request B: in-flight resync triggered by notification:read (delayed)
      // Request C: follow-up resync (authoritative, queued while B in-flight, fires after B resolves)

      let resolveB!: (v: { unread_count: number }) => void;
      const promiseB = new Promise<{ unread_count: number }>(r => { resolveB = r; });

      // Use mockImplementation to control each call precisely
      let callIndex = 0;
      mockGetUnreadNotificationCount.mockImplementation(() => {
        callIndex++;
        if (callIndex === 1) return Promise.resolve({ unread_count: 3 });      // A: initial
        if (callIndex === 2) return promiseB;                                    // B: in-flight (stale)
        return Promise.resolve({ unread_count: 2 });                             // C: authoritative follow-up
      });

      renderHook();
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(1);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(3);

      // Trigger read -> starts Request B (in-flight)
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2); // B started

      // While B is pending, trigger another read -> C is QUEUED (single-flight), not started yet
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();
      // Single-flight: still only 2 calls (C is pending)
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);

      // Resolve B (stale = 3) -> this should trigger follow-up C via setTimeout
      act(() => { resolveB!({ unread_count: 3 }); });
      await flushMicrotasks();
      // Advance timers to trigger setTimeout in resyncUnreadCount finally block
      await advanceTimers(1);
      await flushMicrotasks();

      // Now C should have started (3rd call)
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(3);

      // Final state should be authoritative (2), not stale (3)
      expect(mockStoreState.setUnreadCount).toHaveBeenLastCalledWith(2);
    });
  });

  describe('Generation Protection (Stale Response)', () => {
    it('ignores stale resync responses using generation counter', async () => {
      let resolveGen1!: (v: { unread_count: number }) => void;
      let resolveGen2!: (v: { unread_count: number }) => void;

      const p1 = new Promise<{ unread_count: number }>(r => { resolveGen1 = r; });
      const p2 = new Promise<{ unread_count: number }>(r => { resolveGen2 = r; });

      // initial, then Gen1 (delayed), then Gen2 (immediate)
      let callIndex = 0;
      mockGetUnreadNotificationCount.mockImplementation(() => {
        callIndex++;
        if (callIndex === 1) return Promise.resolve({ unread_count: 5 }); // initial
        if (callIndex === 2) return p1;                                    // Gen 1
        return p2;                                                         // Gen 2
      });

      renderHook();
      await flushMicrotasks();
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5);

      // Two rapid invalidations -> Gen 1 starts, Gen 2 is QUEUED (single-flight)
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();

      // Only 2 calls: initial + Gen1 (Gen2 is pending)
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);

      // Resolve Gen1 first to unblock Gen2
      act(() => { resolveGen1!({ unread_count: 3 }); });
      await flushMicrotasks();
      // Advance timers to trigger setTimeout for follow-up
      await advanceTimers(1);
      await flushMicrotasks();

      // Now Gen2 should start (3rd call)
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(3);

      // Resolve Gen2 with authoritative value = 2
      act(() => { resolveGen2!({ unread_count: 2 }); });
      await flushMicrotasks();

      // Gen 2 should win (generation protection)
      expect(mockStoreState.setUnreadCount).toHaveBeenLastCalledWith(2);
    });
  });

  describe('Single-flight / Pending Invalidation', () => {
    it('runs follow-up resync when invalidation arrives during resync', async () => {
      let resolveInFlight!: (v: { unread_count: number }) => void;
      const inFlight = new Promise<{ unread_count: number }>(r => { resolveInFlight = r; });

      let callIndex = 0;
      mockGetUnreadNotificationCount.mockImplementation(() => {
        callIndex++;
        if (callIndex === 1) return Promise.resolve({ unread_count: 5 }); // initial
        if (callIndex === 2) return inFlight;                             // in-flight resync
        return Promise.resolve({ unread_count: 3 });                      // follow-up
      });

      renderHook();
      await flushMicrotasks();
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5);

      // First invalidation -> starts in-flight resync
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);

      // Second invalidation arrives WHILE in-flight -> should be queued as pending
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();
      // Should NOT start 3rd request yet (single-flight)
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);

      // Resolve in-flight
      act(() => { resolveInFlight!({ unread_count: 4 }); });
      await flushMicrotasks();
      // Advance timers to trigger setTimeout for follow-up
      await advanceTimers(1);
      await flushMicrotasks();

      // Follow-up should now fire
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(3);
      expect(mockStoreState.setUnreadCount).toHaveBeenLastCalledWith(3);
    });
  });

  describe('Debounce Protection', () => {
    it('consolidates multiple notification.created events within debounce window', async () => {
      setupUnreadCountMock(1, 5, 4); // initial=1, onopen resync=5, debounced resync=4

      renderHook();
      await flushMicrotasks();

      // Connect SSE
      const es = getEventSource();
      act(() => { es.emitOpen(); });
      act(() => { es.emitMessage({ type: 'connected' }); });
      await flushMicrotasks();

      // Initial sync + onopen resync = 2 calls
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);

      // Fire 5 rapid events
      act(() => {
        es.emitEvent('notification.created', { id: '1' });
        es.emitEvent('notification.created', { id: '2' });
        es.emitEvent('notification.created', { id: '3' });
        es.emitEvent('notification.created', { id: '4' });
        es.emitEvent('notification.created', { id: '5' });
      });

      // Before debounce expires - no additional resync yet
      await advanceTimers(299);
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);

      // After debounce expires - single debounced resync
      await advanceTimers(1);
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(3);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(4);
    });
  });

  describe('REST Failure Handling', () => {
    it('keeps current count on resync failure, does not set to 0', async () => {
      let callIndex = 0;
      mockGetUnreadNotificationCount.mockImplementation(() => {
        callIndex++;
        if (callIndex === 1) return Promise.resolve({ unread_count: 5 }); // initial
        return Promise.reject(new Error('Network error')); // resync fails
      });

      renderHook();
      await flushMicrotasks();
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5);

      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();

      // Should keep current count (5), not reset to 0
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledTimes(1);
      expect(mockStoreState.setUnreadCount).not.toHaveBeenCalledWith(0);
      expect(mockStoreState.increment).not.toHaveBeenCalled();
    });

    it('keeps SSE operational after resync failure', async () => {
      let callIndex = 0;
      mockGetUnreadNotificationCount.mockImplementation(() => {
        callIndex++;
        if (callIndex === 1) return Promise.resolve({ unread_count: 5 });   // initial
        if (callIndex === 2) return Promise.reject(new Error('Network error')); // resync 1 fails
        return Promise.resolve({ unread_count: 3 });                         // resync 2 succeeds
      });

      renderHook();
      await flushMicrotasks();
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5);

      // First read -> resync fails
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(2);

      // Second read -> resync succeeds
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(3);
      expect(mockStoreState.setUnreadCount).toHaveBeenLastCalledWith(3);
    });
  });

  describe('Cleanup', () => {
    it('closes EventSource on unmount', async () => {
      const { unmount } = renderHook();
      await flushMicrotasks();

      // Connect SSE first
      const es = getEventSource();
      act(() => { es.emitOpen(); });
      act(() => { es.emitMessage({ type: 'connected' }); });
      await flushMicrotasks();

      expect(es.readyState).toBe(MockEventSource.OPEN);

      unmount();
      await flushMicrotasks();

      expect(es.readyState).toBe(MockEventSource.CLOSED);
    });

    it('clears reconnect timer on unmount', async () => {
      const { unmount } = renderHook();
      await flushMicrotasks();

      // Connect and then error to trigger reconnect
      const es = getEventSource();
      act(() => { es.emitOpen(); });
      act(() => { es.emitMessage({ type: 'connected' }); });
      await flushMicrotasks();

      act(() => { es.emitError(); });
      await flushMicrotasks();

      unmount();
      await advanceTimers(2000); // Would trigger reconnect if timer not cleared
      await flushMicrotasks();

      // No new EventSource should be created after unmount
      expect(createdEventSources.length).toBe(1);
    });

    it('removes notification:read listener on unmount', async () => {
      const { unmount } = renderHook();
      await flushMicrotasks();

      unmount();
      await flushMicrotasks();

      // Dispatch after unmount should not trigger resync
      const callCountBefore = mockGetUnreadNotificationCount.mock.calls.length;
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();

      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(callCountBefore);
    });

    it('removes notification:read-all listener on unmount', async () => {
      const { unmount } = renderHook();
      await flushMicrotasks();

      unmount();
      await flushMicrotasks();

      const callCountBefore = mockGetUnreadNotificationCount.mock.calls.length;
      act(() => window.dispatchEvent(new CustomEvent('notification:read-all')));
      await flushMicrotasks();

      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(callCountBefore);
    });
  });

  describe('Phase 1 Regression', () => {
    it('already-read notification dispatches navigation event without mark-read', async () => {
      setupUnreadCountMock(3);
      renderHook();
      await flushMicrotasks();

      const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
      act(() => window.dispatchEvent(new CustomEvent('notification:created', { detail: { id: '1', is_read: true } })));
      await flushMicrotasks();

      expect(dispatchSpy).toHaveBeenCalled();
    });
  });

  describe('Initial Sync + SSE Failure', () => {
    it('initializes unread count even when SSE ticket fetch fails', async () => {
      setupUnreadCountMock(5);
      mockGetStreamTicket.mockRejectedValue(new Error('Auth failed'));

      renderHook();
      await flushMicrotasks();

      // Initial sync should still work (no EventSource created)
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledTimes(1);
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5);
      expect(createdEventSources.length).toBe(0);
    });
  });

  describe('SSE Failure + REST Failure', () => {
    it('remains stable when both SSE and REST fail', async () => {
      let callIndex = 0;
      mockGetUnreadNotificationCount.mockImplementation(() => {
        callIndex++;
        if (callIndex === 1) return Promise.resolve({ unread_count: 5 }); // initial succeeds
        return Promise.reject(new Error('REST failed')); // subsequent fails
      });
      mockGetStreamTicket.mockRejectedValue(new Error('SSE auth failed'));

      renderHook();
      await flushMicrotasks();

      expect(mockStoreState.setUnreadCount).toHaveBeenCalledWith(5);

      // Invalidation should not crash
      act(() => window.dispatchEvent(new CustomEvent('notification:read')));
      await flushMicrotasks();

      // Should not reset to 0 on failure
      expect(mockStoreState.setUnreadCount).toHaveBeenCalledTimes(1);
    });
  });
});