import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { AdminSubscriptionList } from '@/features/admin/components/AdminSubscriptionList'
import { AdminSubscriptionDetailModal } from '@/features/admin/components/AdminSubscriptionDetailModal'
import { getAdminSubscriptions, getAdminSubscription } from '@/api/admin'
import type {
  AdminSubscriptionDetail,
  AdminSubscriptionList as AdminSubscriptionListResponse,
  AdminSubscriptionListItem,
} from '@/types/admin'

vi.mock('@/api/admin')

const noop = () => {}

function makeItem(
  overrides: Partial<AdminSubscriptionListItem> = {},
): AdminSubscriptionListItem {
  return {
    id: 'sub-1',
    user_id: 'user-1',
    user_email: 'buyer@example.com',
    plan_id: 'plan-1',
    plan_name: 'Gói cơ bản',
    status: 'active',
    effective_status: 'active',
    started_at: '2026-01-01T00:00:00Z',
    expires_at: '2026-02-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    max_job_posts: 5,
    max_candidate_searches: 10,
    max_ai_features: 3,
    job_posts_used: 1,
    candidate_searches_used: 2,
    ai_features_used: 0,
    total_subscriptions: 1,
    has_multiple_active: false,
    has_unresolved_payment: false,
    is_entitlement_incident: false,
    incident_subscription_id: null,
    incident_internal_order_id: null,
    incident_amount: null,
    ...overrides,
  }
}

function makeList(items: AdminSubscriptionListItem[]): AdminSubscriptionListResponse {
  return { items, total: items.length, skip: 0, limit: 10 }
}

function makeDetail(item: AdminSubscriptionListItem): AdminSubscriptionDetail {
  return {
    subscription: item,
    history: [
      {
        id: item.id,
        plan_id: item.plan_id,
        plan_name: item.plan_name,
        status: item.status,
        started_at: item.started_at,
        expires_at: item.expires_at,
        created_at: item.created_at,
        max_job_posts: item.max_job_posts,
        max_candidate_searches: item.max_candidate_searches,
        max_ai_features: item.max_ai_features,
        job_posts_used: item.job_posts_used,
        candidate_searches_used: item.candidate_searches_used,
        ai_features_used: item.ai_features_used,
        payments: [],
      },
    ],
    audit_logs: [],
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function renderList(props: { refreshSignal?: number } = {}) {
  return render(
    <AdminSubscriptionList
      refreshSignal={props.refreshSignal}
      onChangePlan={noop}
      onRevoke={noop}
      onViewDetail={noop}
    />,
  )
}

describe('AdminSubscriptionList realtime refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('silently refetches on admin:subscription:changed and keeps existing rows meanwhile', async () => {
    vi.mocked(getAdminSubscriptions).mockResolvedValue(makeList([makeItem()]))
    renderList()

    await waitFor(() =>
      expect(screen.getByText('buyer@example.com')).toBeInTheDocument(),
    )
    expect(getAdminSubscriptions).toHaveBeenCalledTimes(1)

    vi.mocked(getAdminSubscriptions).mockResolvedValue(
      makeList([makeItem({ user_email: 'second@example.com' })]),
    )

    act(() => {
      window.dispatchEvent(
        new CustomEvent('admin:subscription:changed', {
          detail: { user_id: 'user-1', action: 'revoked' },
        }),
      )
    })

    // Existing rows are visible during the debounce window (no skeleton reset).
    expect(screen.getByText('buyer@example.com')).toBeInTheDocument()

    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(screen.getByText('second@example.com')).toBeInTheDocument(),
    )
  })

  it('coalesces a burst of change events into a single silent refetch', async () => {
    vi.mocked(getAdminSubscriptions).mockResolvedValue(makeList([makeItem()]))
    renderList()
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(1))

    act(() => {
      for (let index = 0; index < 5; index += 1) {
        window.dispatchEvent(
          new CustomEvent('admin:subscription:changed', {
            detail: { user_id: `user-${index}` },
          }),
        )
      }
    })

    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(2))
    await act(async () => {
      await sleep(400)
    })
    expect(getAdminSubscriptions).toHaveBeenCalledTimes(2)
  })

  it('ignores an out-of-order stale response', async () => {
    const stale = makeItem({ user_email: 'stale@example.com' })
    const fresh = makeItem({ user_email: 'fresh@example.com', id: 'sub-2' })

    let resolveStale!: (value: AdminSubscriptionListResponse) => void
    const stalePromise = new Promise<AdminSubscriptionListResponse>((resolve) => {
      resolveStale = resolve
    })

    let call = 0
    vi.mocked(getAdminSubscriptions).mockImplementation(() => {
      call += 1
      if (call === 1) return Promise.resolve(makeList([makeItem()]))
      if (call === 2) return stalePromise
      return Promise.resolve(makeList([fresh]))
    })

    renderList()
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(1))

    act(() => {
      window.dispatchEvent(new CustomEvent('admin:subscription:changed'))
    })
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(2))

    act(() => {
      window.dispatchEvent(new CustomEvent('admin:subscription:changed'))
    })
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(3))
    await waitFor(() =>
      expect(screen.getByText('fresh@example.com')).toBeInTheDocument(),
    )

    // The older request resolves late; it must not clobber the newer result.
    await act(async () => {
      resolveStale(makeList([stale]))
      await sleep(0)
    })
    expect(screen.queryByText('stale@example.com')).not.toBeInTheDocument()
    expect(screen.getByText('fresh@example.com')).toBeInTheDocument()
  })

  it('refetches when the stream reconnects', async () => {
    vi.mocked(getAdminSubscriptions).mockResolvedValue(makeList([makeItem()]))
    renderList()
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(1))

    act(() => {
      window.dispatchEvent(new CustomEvent('stream:connected'))
    })
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(2))
  })

  it('refetches when the tab becomes visible again', async () => {
    const original = Object.getOwnPropertyDescriptor(
      Document.prototype,
      'visibilityState',
    )
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    })

    vi.mocked(getAdminSubscriptions).mockResolvedValue(makeList([makeItem()]))
    renderList()
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(1))

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(2))

    if (original) {
      Object.defineProperty(Document.prototype, 'visibilityState', original)
    }
  })

  it('refreshes after a local mutation without losing page/search/filter', async () => {
    vi.mocked(getAdminSubscriptions).mockResolvedValue(makeList([makeItem()]))
    const { rerender } = renderList({ refreshSignal: 0 })
    await waitFor(() => expect(getAdminSubscriptions).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByLabelText('Tìm theo email người dùng'), {
      target: { value: 'buyer@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /tìm kiếm/i }))
    await waitFor(() =>
      expect(getAdminSubscriptions).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'buyer@example.com' }),
      ),
    )
    const callsBefore = vi.mocked(getAdminSubscriptions).mock.calls.length

    rerender(
      <AdminSubscriptionList
        refreshSignal={1}
        onChangePlan={noop}
        onRevoke={noop}
        onViewDetail={noop}
      />,
    )

    await waitFor(() =>
      expect(getAdminSubscriptions).toHaveBeenCalledTimes(callsBefore + 1),
    )
    // Filter + input state survived (no remount reset).
    expect(getAdminSubscriptions).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: 'buyer@example.com' }),
    )
    expect(screen.getByLabelText('Tìm theo email người dùng')).toHaveValue(
      'buyer@example.com',
    )
  })
})

describe('AdminSubscriptionDetailModal realtime refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reloads only for the viewed user and ignores other users event', async () => {
    const item = makeItem()
    vi.mocked(getAdminSubscription).mockResolvedValue(makeDetail(item))

    render(<AdminSubscriptionDetailModal subscription={item} onClose={noop} />)
    await waitFor(() => expect(getAdminSubscription).toHaveBeenCalledTimes(1))

    act(() => {
      window.dispatchEvent(
        new CustomEvent('admin:subscription:changed', {
          detail: { user_id: 'someone-else' },
        }),
      )
    })
    await act(async () => {
      await sleep(400)
    })
    expect(getAdminSubscription).toHaveBeenCalledTimes(1)

    act(() => {
      window.dispatchEvent(
        new CustomEvent('admin:subscription:changed', {
          detail: { user_id: 'user-1' },
        }),
      )
    })
    await waitFor(() => expect(getAdminSubscription).toHaveBeenCalledTimes(2))
  })

  it('ignores a stale response when the viewed record changes', async () => {
    const itemA = makeItem({ id: 'sub-A', user_id: 'user-A', user_email: 'a@example.com', plan_name: 'Gói A' })
    const itemB = makeItem({ id: 'sub-B', user_id: 'user-B', user_email: 'b@example.com', plan_name: 'Gói B' })

    let resolveA!: (value: AdminSubscriptionDetail) => void
    const promiseA = new Promise<AdminSubscriptionDetail>((resolve) => {
      resolveA = resolve
    })

    vi.mocked(getAdminSubscription).mockImplementation((id: string) => {
      if (id === 'sub-A') return promiseA
      return Promise.resolve(makeDetail(itemB))
    })

    const { rerender } = render(
      <AdminSubscriptionDetailModal subscription={itemA} onClose={noop} />,
    )

    rerender(<AdminSubscriptionDetailModal subscription={itemB} onClose={noop} />)

    await waitFor(() =>
      expect(screen.getAllByText('Gói B').length).toBeGreaterThan(0),
    )

    await act(async () => {
      resolveA(makeDetail(itemA))
      await sleep(0)
    })
    expect(screen.queryByText('Gói A')).not.toBeInTheDocument()
    expect(screen.getAllByText('Gói B').length).toBeGreaterThan(0)
  })
})
