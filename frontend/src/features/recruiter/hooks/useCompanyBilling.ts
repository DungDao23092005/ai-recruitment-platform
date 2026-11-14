import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getCompanySubscriptionHistory,
  getCompanyUsages,
} from '@/api/subscriptions'
import { useOptionalWorkspace } from '@/contexts/WorkspaceContext'
import type {
  CompanyUsageHistoryResponse,
  CompanyUsageQueryParams,
} from '@/types/subscription'
import type { PaymentOrderRead } from '@/types/payment'

export interface UseCompanyUsagesResult {
  data: CompanyUsageHistoryResponse | null
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function useCompanyUsages(
  params: CompanyUsageQueryParams,
  enabled = true,
): UseCompanyUsagesResult {
  const workspace = useOptionalWorkspace()
  const selectedCompanyId = workspace?.selectedCompanyId ?? null

  const [data, setData] = useState<CompanyUsageHistoryResponse | null>(null)
  const [isLoading, setIsLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  const isMountedRef = useRef(true)
  const generationRef = useRef(0)

  const {
    page,
    page_size,
    start_date,
    end_date,
    feature_type,
    user_id,
  } = params

  const fetchUsages = useCallback(async () => {
    const generation = ++generationRef.current
    setIsLoading(true)
    setError(null)

    try {
      const result = await getCompanyUsages({
        page,
        page_size,
        start_date,
        end_date,
        feature_type,
        user_id,
      })
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }
      setData(result)
    } catch (err) {
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }
      setError(
        err instanceof Error
          ? err.message
          : 'Không thể tải lịch sử sử dụng.',
      )
    } finally {
      if (isMountedRef.current && generationRef.current === generation) {
        setIsLoading(false)
      }
    }
  }, [end_date, feature_type, page, page_size, start_date, user_id])

  useEffect(() => {
    isMountedRef.current = true

    if (!enabled) {
      generationRef.current += 1
      setData(null)
      setIsLoading(false)
      setError(null)
      return () => {
        isMountedRef.current = false
      }
    }

    void fetchUsages()

    return () => {
      isMountedRef.current = false
    }
  }, [enabled, fetchUsages, selectedCompanyId])

  const refetch = useCallback(() => {
    void fetchUsages()
  }, [fetchUsages])

  return { data, isLoading, error, refetch }
}

export interface UseCompanyPaymentHistoryResult {
  orders: PaymentOrderRead[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function useCompanyPaymentHistory(
  enabled = true,
): UseCompanyPaymentHistoryResult {
  const workspace = useOptionalWorkspace()
  const selectedCompanyId = workspace?.selectedCompanyId ?? null

  const [orders, setOrders] = useState<PaymentOrderRead[]>([])
  const [isLoading, setIsLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  const isMountedRef = useRef(true)
  const generationRef = useRef(0)

  const fetchOrders = useCallback(async () => {
    const generation = ++generationRef.current
    setIsLoading(true)
    setError(null)

    try {
      const result = await getCompanySubscriptionHistory()
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }
      setOrders(result)
    } catch (err) {
      if (!isMountedRef.current || generationRef.current !== generation) {
        return
      }
      setError(
        err instanceof Error
          ? err.message
          : 'Không thể tải lịch sử thanh toán.',
      )
    } finally {
      if (isMountedRef.current && generationRef.current === generation) {
        setIsLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    isMountedRef.current = true

    if (!enabled) {
      generationRef.current += 1
      setOrders([])
      setIsLoading(false)
      setError(null)
      return () => {
        isMountedRef.current = false
      }
    }

    void fetchOrders()

    return () => {
      isMountedRef.current = false
    }
  }, [enabled, fetchOrders, selectedCompanyId])

  const refetch = useCallback(() => {
    void fetchOrders()
  }, [fetchOrders])

  return { orders, isLoading, error, refetch }
}
