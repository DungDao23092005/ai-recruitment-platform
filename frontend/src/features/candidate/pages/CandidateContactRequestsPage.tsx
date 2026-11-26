import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  CheckCircle2,
  Clock,
  Building2,
  Calendar,
  ShieldCheck,
  XCircle,
  AlertCircle,
  Ban,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import {
  acceptContactRequest,
  declineContactRequest,
  getCandidateIncomingContactRequests,
  revokeContactAuthorization,
} from '@/api/contactRequests'
import { CONTACT_REQUEST_UPDATED_DOM_EVENT } from '@/hooks/useNotificationStream'
import type {
  CandidateContactRequestRead,
  ContactRequestStatus,
} from '@/types/ai'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'

type FilterKey = 'all' | ContactRequestStatus

const FILTER_TABS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'pending', label: 'Chờ phản hồi' },
  { key: 'accepted', label: 'Đã chấp nhận' },
  { key: 'declined', label: 'Đã từ chối' },
  { key: 'revoked', label: 'Đã thu hồi' },
]

export function CandidateContactRequestsPage() {
  const [searchParams] = useSearchParams()
  const targetId = searchParams.get('id')

  const [requests, setRequests] = useState<CandidateContactRequestRead[]>([])
  const [activeFilter, setActiveFilter] = useState<FilterKey>('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<{
    id: string
    type: 'success' | 'error'
    text: string
  } | null>(null)

  const loadRequests = async (statusFilter?: FilterKey) => {
    setIsLoading(true)
    setError(null)
    try {
      const filter =
        statusFilter && statusFilter !== 'all' ? statusFilter : undefined
      const data = await getCandidateIncomingContactRequests(filter)
      setRequests(data)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void loadRequests(activeFilter)
  }, [activeFilter])

  useEffect(() => {
    const handleContactRequestUpdated = () => {
      void loadRequests(activeFilter)
    }

    window.addEventListener(
      CONTACT_REQUEST_UPDATED_DOM_EVENT,
      handleContactRequestUpdated,
    )
    return () => {
      window.removeEventListener(
        CONTACT_REQUEST_UPDATED_DOM_EVENT,
        handleContactRequestUpdated,
      )
    }
  }, [activeFilter])

  useEffect(() => {
    if (!isLoading && requests.length > 0 && targetId) {
      const el = document.getElementById(`contact-request-${targetId}`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
  }, [isLoading, requests, targetId])

  const handleAccept = async (requestId: string) => {
    setActionLoadingId(requestId)
    setActionMessage(null)
    try {
      const updated = await acceptContactRequest(requestId)
      setRequests((prev) =>
        prev.map((r) => (r.id === requestId ? { ...r, ...updated } : r)),
      )
      setActionMessage({
        id: requestId,
        type: 'success',
        text: 'Đã chấp nhận yêu cầu kết nối thành công.',
      })
    } catch (err) {
      setActionMessage({
        id: requestId,
        type: 'error',
        text: getFriendlyErrorMessage(err),
      })
    } finally {
      setActionLoadingId(null)
    }
  }

  const handleDecline = async (requestId: string) => {
    setActionLoadingId(requestId)
    setActionMessage(null)
    try {
      const updated = await declineContactRequest(requestId)
      setRequests((prev) =>
        prev.map((r) => (r.id === requestId ? { ...r, ...updated } : r)),
      )
      setActionMessage({
        id: requestId,
        type: 'success',
        text: 'Đã từ chối yêu cầu kết nối.',
      })
    } catch (err) {
      setActionMessage({
        id: requestId,
        type: 'error',
        text: getFriendlyErrorMessage(err),
      })
    } finally {
      setActionLoadingId(null)
    }
  }

  const handleRevoke = async (requestId: string) => {
    setActionLoadingId(requestId)
    setActionMessage(null)
    try {
      const updated = await revokeContactAuthorization(requestId)
      setRequests((prev) =>
        prev.map((r) => (r.id === requestId ? { ...r, ...updated } : r)),
      )
      setActionMessage({
        id: requestId,
        type: 'success',
        text: 'Đã thu hồi quyền xem thông tin liên hệ thành công.',
      })
    } catch (err) {
      setActionMessage({
        id: requestId,
        type: 'error',
        text: getFriendlyErrorMessage(err),
      })
    } finally {
      setActionLoadingId(null)
    }
  }

  const renderStatusBadge = (status: ContactRequestStatus) => {
    switch (status) {
      case 'accepted':
        return (
          <Badge variant="success" className="gap-1">
            <ShieldCheck className="h-3.5 w-3.5" />
            Đã chấp nhận
          </Badge>
        )
      case 'pending':
        return (
          <Badge variant="warning" className="gap-1">
            <Clock className="h-3.5 w-3.5" />
            Chờ phản hồi
          </Badge>
        )
      case 'declined':
        return (
          <Badge variant="destructive" className="gap-1">
            <XCircle className="h-3.5 w-3.5" />
            Đã từ chối
          </Badge>
        )
      case 'revoked':
        return (
          <Badge variant="neutral" className="gap-1">
            <Ban className="h-3.5 w-3.5" />
            Đã thu hồi quyền
          </Badge>
        )
      case 'expired':
        return (
          <Badge variant="neutral" className="gap-1">
            <AlertCircle className="h-3.5 w-3.5" />
            Đã hết hạn
          </Badge>
        )
      default:
        return null
    }
  }

  return (
    <div className="container py-8 max-w-4xl space-y-6">
      <PageHeader
        title="Yêu cầu kết nối từ nhà tuyển dụng"
        description="Quản lý quyền xem thông tin liên hệ của bạn đối với các nhà tuyển dụng tìm kiếm ứng viên."
      />

      {/* Filter Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border/70 pb-3">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveFilter(tab.key)}
            className={cn(
              'px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors',
              activeFilter === tab.key
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-16 space-y-3">
          <Spinner className="h-8 w-8 text-primary" />
          <p className="text-sm text-muted-foreground">
            Đang tải danh sách yêu cầu kết nối...
          </p>
        </div>
      ) : error ? (
        <ErrorBanner message={error} onRetry={() => void loadRequests(activeFilter)} />
      ) : requests.length === 0 ? (
        <EmptyState
          icon={<Building2 className="h-6 w-6" />}
          title="Chưa có yêu cầu kết nối nào"
          description={
            activeFilter === 'all'
              ? 'Khi các nhà tuyển dụng tìm thấy hồ sơ của bạn và gửi yêu cầu, thông tin sẽ xuất hiện tại đây.'
              : 'Không có yêu cầu kết nối nào phù hợp với bộ lọc hiện tại.'
          }
        />
      ) : (
        <div className="space-y-4">
          {requests.map((req) => {
            const isTarget = req.id === targetId
            return (
              <div
                key={req.id}
                id={`contact-request-${req.id}`}
                data-testid={isTarget ? 'target-contact-request-card' : undefined}
                className={cn(
                  'rounded-xl border border-border/70 bg-card p-5 shadow-xs space-y-4 transition-all hover:border-border',
                  isTarget && 'ring-2 ring-primary border-primary bg-primary/5',
                )}
              >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-bold text-base text-foreground truncate">
                      {req.company_name || 'Doanh nghiệp'}
                    </h3>
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                      <Calendar className="h-3 w-3" />
                      Gửi lúc {new Date(req.created_at).toLocaleString('vi-VN')}
                    </p>
                  </div>
                </div>

                <div className="self-start sm:self-auto">
                  {renderStatusBadge(req.status)}
                </div>
              </div>

              {/* Status explanation */}
              <div className="rounded-lg bg-muted/30 p-3 text-xs text-muted-foreground leading-relaxed">
                {req.status === 'pending' ? (
                  <span>
                    Doanh nghiệp muốn xem email và số điện thoại của bạn để liên hệ phỏng vấn/tuyển dụng. Yêu cầu này sẽ tự động hết hạn vào ngày{' '}
                    <strong>
                      {new Date(req.expires_at).toLocaleDateString('vi-VN')}
                    </strong>.
                  </span>
                ) : req.status === 'accepted' ? (
                  <span className="text-foreground">
                    Doanh nghiệp đã được bạn cấp quyền xem thông tin liên hệ. Mọi lượt truy cập xem email và số điện thoại đều được ghi nhật ký kiểm toán.
                  </span>
                ) : req.status === 'declined' ? (
                  <span>
                    Bạn đã từ chối yêu cầu kết nối này. Doanh nghiệp sẽ không thể xem email hay số điện thoại của bạn.
                  </span>
                ) : req.status === 'revoked' ? (
                  <span>
                    Bạn đã thu hồi quyền xem thông tin liên hệ. Doanh nghiệp không còn quyền truy cập thông tin liên hệ của bạn.
                  </span>
                ) : (
                  <span>Yêu cầu này đã hết hạn thời gian phản hồi.</span>
                )}
              </div>

              {/* Feedback Alert for this request */}
              {actionMessage && actionMessage.id === req.id ? (
                <div
                  className={cn(
                    'rounded-lg p-2.5 text-xs font-medium',
                    actionMessage.type === 'success'
                      ? 'bg-success/10 text-success'
                      : 'bg-destructive/10 text-destructive',
                  )}
                  role={actionMessage.type === 'success' ? 'status' : 'alert'}
                >
                  {actionMessage.text}
                </div>
              ) : null}

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center justify-end gap-2.5 pt-1">
                {req.status === 'pending' ? (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDecline(req.id)}
                      disabled={actionLoadingId === req.id}
                      className="text-xs"
                    >
                      Từ chối
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleAccept(req.id)}
                      isLoading={actionLoadingId === req.id}
                      disabled={actionLoadingId === req.id}
                      className="text-xs gap-1"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Chấp nhận
                    </Button>
                  </>
                ) : req.status === 'accepted' ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleRevoke(req.id)}
                    isLoading={actionLoadingId === req.id}
                    disabled={actionLoadingId === req.id}
                    className="text-xs text-destructive hover:bg-destructive/10"
                  >
                    <Ban className="h-3.5 w-3.5 mr-1" />
                    Thu hồi quyền
                  </Button>
                ) : null}
              </div>
            </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
