import apiClient from '@/api/client'
import type { Subscription } from '@/types/subscription'

export async function getMySubscription(): Promise<Subscription | null> {
  try {
    return await apiClient.get<Subscription, Subscription | null>('/subscriptions/me')
  } catch (error) {
    if ((error as { response?: { status: number } }).response?.status === 404) {
      return null
    }
    throw error
  }
}