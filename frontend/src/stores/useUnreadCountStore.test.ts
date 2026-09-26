/// <reference types="vitest/globals" />
import { describe, it, expect, beforeEach } from 'vitest';
import { act } from '@testing-library/react';
import { useUnreadCountStore } from '@/stores/useUnreadCountStore';

describe('useUnreadCountStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    act(() => {
      useUnreadCountStore.getState().reset();
    });
  });

  it('initial unreadCount should be 0', () => {
    expect(useUnreadCountStore.getState().unreadCount).toBe(0);
  });

  it('setUnreadCount should update unreadCount', () => {
    act(() => {
      useUnreadCountStore.getState().setUnreadCount(5);
    });
    expect(useUnreadCountStore.getState().unreadCount).toBe(5);
  });

  it('setUnreadCount with negative value should clamp to 0', () => {
    act(() => {
      useUnreadCountStore.getState().setUnreadCount(-1);
    });
    expect(useUnreadCountStore.getState().unreadCount).toBe(0);
  });

  it('increment should increase unreadCount by 1', () => {
    act(() => {
      useUnreadCountStore.getState().setUnreadCount(3);
    });
    act(() => {
      useUnreadCountStore.getState().increment();
    });
    expect(useUnreadCountStore.getState().unreadCount).toBe(4);
  });

  it('increment from 0 should result in 1', () => {
    act(() => {
      useUnreadCountStore.getState().increment();
    });
    expect(useUnreadCountStore.getState().unreadCount).toBe(1);
  });

  it('decrement should decrease unreadCount by 1', () => {
    act(() => {
      useUnreadCountStore.getState().setUnreadCount(5);
    });
    act(() => {
      useUnreadCountStore.getState().decrement();
    });
    expect(useUnreadCountStore.getState().unreadCount).toBe(4);
  });

  it('decrement should not go below 0', () => {
    act(() => {
      useUnreadCountStore.getState().decrement();
    });
    expect(useUnreadCountStore.getState().unreadCount).toBe(0);
  });

  it('reset should set unreadCount to 0', () => {
    act(() => {
      useUnreadCountStore.getState().setUnreadCount(10);
    });
    act(() => {
      useUnreadCountStore.getState().reset();
    });
    expect(useUnreadCountStore.getState().unreadCount).toBe(0);
  });
});
