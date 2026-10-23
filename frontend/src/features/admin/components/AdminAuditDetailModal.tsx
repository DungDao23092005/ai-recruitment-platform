import { LockKeyhole, LockKeyholeOpen, ScrollText, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import type { AdminAuditAction, AdminAuditLog } from '@/types/admin'

const ACTION_LABELS: Record<AdminAuditAction, string> = {
  user_lock: 'Khóa tài khoản',
  user_unlock: 'Mở khóa tài khoản',
  user_delete: 'Xóa tài khoản',
}

const ACTION_VARIANTS: Record<
  AdminAuditAction,
  'warning' | 'success' | 'destructive'
> = {
  user_lock: 'warning',
  user_unlock: 'success',
  user_delete: 'destructive',
}

const ACTION_ICONS = {
  user_lock: LockKeyhole,
  user_unlock: LockKeyholeOpen,
  user_delete: Trash2,
} satisfies Record<AdminAuditAction, typeof ScrollText>

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Không rõ'
  }
  return date.toLocaleString('vi-VN', {
    dateStyle: 'long',
    timeStyle: 'medium',
  })
}

export interface AdminAuditDetailModalProps {
  log: AdminAuditLog
  onClose: () => void
}

export function AdminAuditDetailModal({
  log,
  onClose,
}: AdminAuditDetailModalProps) {
  const ActionIcon = ACTION_ICONS[log.action]
  const detailsText =
    log.details && Object.keys(log.details).length > 0
      ? JSON.stringify(log.details, null, 2)
      : null

  return (
    <Modal
      onClose={onClose}
      size="lg"
      ariaLabel="Chi tiết bản ghi nhật ký quản trị"
      title={
        <span className="flex items-center gap-2">
          <ScrollText className="h-5 w-5 text-primary" aria-hidden="true" />
          Chi tiết bản ghi
        </span>
      }
      description="Bản ghi chỉ đọc, không thể chỉnh sửa hoặc xóa."
      footer={
        <Button type="button" variant="outline" onClick={onClose}>
          Đóng
        </Button>
      }
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
          <Badge variant={ACTION_VARIANTS[log.action]} className="gap-1.5">
            <ActionIcon className="h-3.5 w-3.5" aria-hidden="true" />
            {ACTION_LABELS[log.action]}
          </Badge>
          <code className="break-all font-mono text-xs text-muted-foreground">
            #{log.id}
          </code>
        </div>

        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Thời gian
            </dt>
            <dd className="mt-1 text-sm text-foreground">
              <time dateTime={log.created_at}>
                {formatTimestamp(log.created_at)}
              </time>
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Hành động
            </dt>
            <dd className="mt-1 text-sm text-foreground">
              {ACTION_LABELS[log.action]}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Quản trị viên
            </dt>
            <dd className="mt-1 text-sm text-foreground">
              <span className="break-all">
                {log.admin_email ?? 'Không xác định'}
              </span>
              <code className="mt-1 block break-all font-mono text-xs text-muted-foreground">
                {log.admin_id}
              </code>
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Đối tượng
            </dt>
            <dd className="mt-1 text-sm text-foreground">
              <span className="break-all">
                {log.target_user_email ?? 'Không xác định'}
              </span>
              <code className="mt-1 block break-all font-mono text-xs text-muted-foreground">
                {log.target_user_id}
              </code>
            </dd>
          </div>
        </dl>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Lý do
          </h3>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-foreground">
            {log.reason ?? 'Không có lý do được ghi nhận.'}
          </p>
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Chi tiết kỹ thuật
          </h3>
          {detailsText ? (
            <pre
              aria-label="Chi tiết kỹ thuật"
              className="mt-2 max-h-64 overflow-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs text-foreground"
            >
              {detailsText}
            </pre>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">
              Không có dữ liệu bổ sung.
            </p>
          )}
        </section>

        <p className="rounded-lg border border-dashed bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          Bản ghi này chỉ chứa thông tin ngữ cảnh đã được làm sạch. Mật khẩu,
          token và email gốc của tài khoản đã xóa không được lưu tại đây.
        </p>
      </div>
    </Modal>
  )
}
