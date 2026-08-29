import { useCallback, useEffect, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Search,
  ShieldCheck,
  Unlock,
  Users,
  Trash2,
} from 'lucide-react'
import { getAdminUsers } from '@/api/admin'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { UserDeactivateModal } from '@/features/admin/components/UserDeactivateModal'
import { UserActivateModal } from '@/features/admin/components/UserActivateModal'
import { UserDeleteModal } from '@/features/admin/components/UserDeleteModal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { USER_ROLE_LABELS } from '@/types/auth'
import type { UserRole } from '@/types/auth'
import type { AdminUser, AdminUserList } from '@/types/admin'

export const ADMIN_USER_PAGE_SIZE = 10

type RoleFilter = '' | UserRole

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; data: AdminUserList }

type ActionType = 'lock' | 'unlock' | 'delete'

type ActionState = {
  type: ActionType
  user: AdminUser
} | null

const ROLE_BADGE_VARIANT: Record<
  UserRole,
  'ai-gradient' | 'info' | 'neutral'
> = {
  admin: 'ai-gradient',
  recruiter: 'info',
  candidate: 'neutral',
}

function formatCreatedAt(dateString: string): string {
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleDateString('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function AdminUsersPage() {
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [role, setRole] = useState<RoleFilter>('')
  const [actionState, setActionState] = useState<ActionState>(null)

  const load = useCallback(async () => {
    setListState({ kind: 'loading' })
    try {
      const data = await getAdminUsers({
        skip: (page - 1) * ADMIN_USER_PAGE_SIZE,
        limit: ADMIN_USER_PAGE_SIZE,
        search: searchQuery.trim() || undefined,
        role: role || undefined,
      })
      setListState({ kind: 'success', data })
    } catch (err) {
      setListState({ kind: 'error', message: getFriendlyErrorMessage(err) })
    }
  }, [page, searchQuery, role])

  useEffect(() => {
    void load()
  }, [load])

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    setPage(1)
    setSearchQuery(search.trim())
  }

  const handleRoleChange = (value: string) => {
    setRole(value as RoleFilter)
    setPage(1)
  }

  const handleActionComplete = () => {
    setActionState(null)
    void load()
  }

  const handleOpenLockModal = (user: AdminUser) => {
    setActionState({ type: 'lock', user })
  }

  const handleOpenUnlockModal = (user: AdminUser) => {
    setActionState({ type: 'unlock', user })
  }

  const handleOpenDeleteModal = (user: AdminUser) => {
    setActionState({ type: 'delete', user })
  }

  const totalPages = Math.max(
    1,
    Math.ceil((listState.kind === 'success' ? listState.data.total : 0) /
      ADMIN_USER_PAGE_SIZE),
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Quản trị viên"
        title="Quản lý người dùng"
        description="Xem danh sách tài khoản, tìm kiếm và khóa tài khoản người dùng trên nền tảng."
      />

      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        aria-label="Tìm kiếm người dùng"
      >
        <div className="w-full sm:max-w-xs">
          <Input
            id="admin-user-search"
            name="search"
            type="search"
            placeholder="Tìm theo email..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Tìm theo email"
          />
        </div>
        <div className="w-full sm:max-w-[11rem]">
          <Select
            id="admin-user-role"
            name="role"
            value={role}
            onChange={(event) => handleRoleChange(event.target.value)}
            aria-label="Lọc theo vai trò"
          >
            <option value="">Tất cả vai trò</option>
            <option value="candidate">Ứng viên</option>
            <option value="recruiter">Nhà tuyển dụng</option>
            <option value="admin">Quản trị viên</option>
          </Select>
        </div>
        <Button type="submit">
          <Search className="h-4 w-4" aria-hidden="true" />
          Tìm kiếm
        </Button>
      </form>

      {listState.kind === 'loading' ? (
        <Card>
          <CardContent className="space-y-3 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-10 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {listState.kind === 'error' ? (
        <ErrorBanner message={listState.message} onRetry={load} />
      ) : null}

      {listState.kind === 'success' ? (
        <>
          {listState.data.items.length === 0 ? (
            <EmptyState
              icon={<Users className="h-6 w-6" aria-hidden="true" />}
              title="Không tìm thấy người dùng"
              description={
                searchQuery || role
                  ? 'Không có tài khoản nào khớp với bộ lọc hiện tại. Hãy điều chỉnh tìm kiếm để xem thêm kết quả.'
                  : 'Chưa có tài khoản nào trên nền tảng.'
              }
            />
          ) : (
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th scope="col" className="px-4 py-3 font-medium">
                        Người dùng
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Vai trò
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Trạng thái
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Ngày tạo
                      </th>
                      <th scope="col" className="px-4 py-3 text-right font-medium">
                        Hành động
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {listState.data.items.map((user) => (
                      <tr
                        key={user.id}
                        className="border-b last:border-b-0 hover:bg-muted/40"
                      >
                        <td className="px-4 py-3">
                          <span className="flex items-center gap-2">
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                              {user.email.charAt(0).toUpperCase()}
                            </span>
                            <span className="truncate">{user.email}</span>
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={ROLE_BADGE_VARIANT[user.role]}>
                            {USER_ROLE_LABELS[user.role]}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          {user.is_active ? (
                            <Badge variant="success">Đang hoạt động</Badge>
                          ) : (
                            <Badge variant="destructive">Đã khóa</Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatCreatedAt(user.created_at) || 'Không rõ'}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {user.is_active ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => handleOpenLockModal(user)}
                                aria-label={`Khóa tài khoản ${user.email}`}
                              >
                                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                                Khóa tài khoản
                              </Button>
                            ) : (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => handleOpenUnlockModal(user)}
                                aria-label={`Mở khóa tài khoản ${user.email}`}
                              >
                                <Unlock className="h-3.5 w-3.5" aria-hidden="true" />
                                Mở khóa
                              </Button>
                            )}
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => handleOpenDeleteModal(user)}
                              aria-label={`Xóa tài khoản ${user.email}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                              Xóa tài khoản
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

          {totalPages > 1 ? (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                aria-label="Trang trước"
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Trước
              </Button>
              <span className="px-2 text-sm text-muted-foreground">
                Trang {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
                aria-label="Trang sau"
              >
                Sau
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          ) : null}
        </>
      ) : null}

      {actionState ? (
        actionState.type === 'lock' ? (
          <UserDeactivateModal
            user={actionState.user}
            onClose={() => setActionState(null)}
            onSuccess={handleActionComplete}
          />
        ) : actionState.type === 'unlock' ? (
          <UserActivateModal
            user={actionState.user}
            onClose={() => setActionState(null)}
            onSuccess={handleActionComplete}
          />
        ) : (
          <UserDeleteModal
            user={actionState.user}
            onClose={() => setActionState(null)}
            onSuccess={handleActionComplete}
          />
        )
      ) : null}
    </div>
  )
}