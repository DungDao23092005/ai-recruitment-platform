import apiClient from '@/api/client';
import type { Notification, UnreadCountResponse, MarkAllReadResponse } from '@/types/notification';

export interface GetNotificationsParams {
  skip?: number;
  limit?: number;
}

export async function getNotifications(
  params: GetNotificationsParams = {}
): Promise<Notification[]> {
  return apiClient.get<Notification[], Notification[]>('/notifications', { params });
}

export async function getUnreadNotificationCount(): Promise<UnreadCountResponse> {
  return apiClient.get<UnreadCountResponse, UnreadCountResponse>('/notifications/unread-count');
}

export async function markNotificationRead(
  notificationId: string
): Promise<Notification> {
  return apiClient.patch<Notification, Notification>(
    `/notifications/${notificationId}/read`
  );
}

export async function markAllNotificationsRead(): Promise<MarkAllReadResponse> {
  return apiClient.patch<MarkAllReadResponse, MarkAllReadResponse>(
    '/notifications/read-all'
  );
}