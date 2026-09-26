import { create } from 'zustand';

interface UnreadCountState {
  unreadCount: number;
  setUnreadCount: (count: number) => void;
  increment: () => void;
  decrement: () => void;
  reset: () => void;
}

const store = (set: any) => ({
  unreadCount: 0,
  setUnreadCount: (count: number) =>
    set({ unreadCount: Math.max(0, count) }),
  increment: () =>
    set((state: UnreadCountState) => ({
      unreadCount: state.unreadCount + 1,
    })),
  decrement: () =>
    set((state: UnreadCountState) => ({
      unreadCount: Math.max(0, state.unreadCount - 1),
    })),
  reset: () =>
    set({ unreadCount: 0 }),
});

const useUnreadCountStore = create<UnreadCountState>(store);

export { useUnreadCountStore };
