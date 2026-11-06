import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { MailPlus, ShieldCheck, UserMinus, Users } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  createWorkspaceInvitation,
  getWorkspaceInvitations,
  getWorkspaceMembers,
  revokeWorkspaceInvitation,
  revokeWorkspaceMember,
  updateWorkspaceMemberRole,
} from '@/api/workspaces'
import { useAuth } from '@/contexts/AuthContext'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { getFriendlyErrorMessage } from '@/utils/errors'
import {
  INVITATION_STATUS_LABELS,
  MEMBERSHIP_ROLE_LABELS,
  MEMBERSHIP_STATUS_LABELS,
  type MembershipRole,
  type WorkspaceInvitation,
  type WorkspaceMember,
} from '@/types/workspace'

export function WorkspaceMembersPage() {
  const { currentUser } = useAuth()
  const { selectedWorkspace, refreshWorkspaces } = useWorkspace()
  const [members, setMembers] = useState<WorkspaceMember[]>([])
  const [invitations, setInvitations] = useState<WorkspaceInvitation[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<MembershipRole>('recruiter')
  const [isInviting, setIsInviting] = useState(false)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const isCompanyAdmin = useMemo(() => {
    if (!selectedWorkspace) return false
    return (
      selectedWorkspace.is_platform_admin ||
      selectedWorkspace.role === 'admin'
    )
  }, [selectedWorkspace])

  const isCompanyManager = useMemo(() => {
    if (!selectedWorkspace) return false
    return (
      selectedWorkspace.is_platform_admin ||
      selectedWorkspace.role === 'admin' ||
      selectedWorkspace.role === 'recruiter'
    )
  }, [selectedWorkspace])

  const loadWorkspaceData = useCallback(async () => {
    if (!selectedWorkspace || !isCompanyManager) {
      setMembers([])
      setInvitations([])
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      const [memberList, invitationList] = await Promise.all([
        getWorkspaceMembers(),
        isCompanyAdmin
          ? getWorkspaceInvitations()
          : Promise.resolve<WorkspaceInvitation[]>([]),
      ])
      setMembers(memberList)
      setInvitations(invitationList)
    } catch (loadError) {
      setError(getFriendlyErrorMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }, [isCompanyAdmin, isCompanyManager, selectedWorkspace])

  useEffect(() => {
    void loadWorkspaceData()
  }, [loadWorkspaceData, selectedWorkspace?.company_id])

  const handleInvite = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSuccessMessage(null)
    setIsInviting(true)
    try {
      await createWorkspaceInvitation({ email: email.trim(), role })
      setEmail('')
      setSuccessMessage('Đã gửi lời mời tham gia công ty.')
      await loadWorkspaceData()
    } catch (inviteError) {
      setError(getFriendlyErrorMessage(inviteError))
    } finally {
      setIsInviting(false)
    }
  }

  const handleRevokeMember = async (member: WorkspaceMember) => {
    if (
      !window.confirm(
        `Thu hồi quyền truy cập của ${member.email} khỏi công ty?`,
      )
    ) {
      return
    }
    setError(null)
    try {
      await revokeWorkspaceMember(member.membership_id)
      await loadWorkspaceData()
      await refreshWorkspaces()
    } catch (revokeError) {
      setError(getFriendlyErrorMessage(revokeError))
    }
  }

  const handleRoleChange = async (
    member: WorkspaceMember,
    nextRole: MembershipRole,
  ) => {
    if (!isCompanyAdmin || nextRole === member.role) {
      return
    }
    setError(null)
    setSuccessMessage(null)
    try {
      await updateWorkspaceMemberRole(member.membership_id, nextRole)
      setSuccessMessage(
        `Đã cập nhật vai trò của ${member.email} thành ${MEMBERSHIP_ROLE_LABELS[nextRole]}.`,
      )
      await loadWorkspaceData()
      await refreshWorkspaces()
    } catch (updateError) {
      setError(getFriendlyErrorMessage(updateError))
    }
  }

  const handleRevokeInvitation = async (invitation: WorkspaceInvitation) => {
    if (!window.confirm(`Thu hồi lời mời của ${invitation.email}?`)) {
      return
    }
    setError(null)
    try {
      await revokeWorkspaceInvitation(invitation.id)
      await loadWorkspaceData()
    } catch (revokeError) {
      setError(getFriendlyErrorMessage(revokeError))
    }
  }

  if (!selectedWorkspace) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Không gian làm việc"
          title="Thành viên công ty"
          description="Chọn một công ty để quản lý thành viên."
        />
        <EmptyState
          icon={<Users className="h-6 w-6" aria-hidden="true" />}
          title="Chưa chọn công ty"
          description="Chọn công ty ở thanh điều hướng phía trên."
        />
      </div>
    )
  }

  if (!isCompanyManager) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow={selectedWorkspace.company_name}
          title="Thành viên công ty"
          description="Chỉ quản trị viên và nhà tuyển dụng của công ty mới có thể xem thành viên."
        />
        <EmptyState
          icon={<ShieldCheck className="h-6 w-6" aria-hidden="true" />}
          title="Không đủ quyền"
          description="Bạn cần quyền quản trị viên hoặc nhà tuyển dụng của công ty này."
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={selectedWorkspace.company_name}
        title="Thành viên công ty"
        description="Mời đồng nghiệp và quản lý quyền truy cập vào không gian làm việc."
      />

      {error ? (
        <ErrorBanner
          message={error}
          onRetry={() => void loadWorkspaceData()}
        />
      ) : null}
      {successMessage ? (
        <p
          role="status"
          className="rounded-md bg-success/10 px-3 py-2 text-sm font-medium text-success"
        >
          {successMessage}
        </p>
      ) : null}

      {!isCompanyAdmin ? (
        <p
          role="status"
          className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground"
        >
          Bạn có quyền xem thành viên. Chỉ quản trị viên mới có thể mời, đổi
          vai trò hoặc thu hồi quyền truy cập.
        </p>
      ) : null}

      {isCompanyAdmin ? (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MailPlus className="h-5 w-5 text-primary" aria-hidden="true" />
            Mời thành viên
          </CardTitle>
          <CardDescription>
            Lời mời có thời hạn và chỉ dùng được một lần.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleInvite}
            className="grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end"
          >
            <Input
              type="email"
              name="invite-email"
              label="Email"
              placeholder="dongnghiep@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <Select
              name="invite-role"
              label="Vai trò"
              value={role}
              onChange={(event) =>
                setRole(event.target.value as MembershipRole)
              }
            >
              <option value="recruiter">Nhà tuyển dụng</option>
              <option value="interviewer">Người phỏng vấn</option>
              <option value="admin">Quản trị viên</option>
            </Select>
            <Button type="submit" isLoading={isInviting}>
              Gửi lời mời
            </Button>
          </form>
        </CardContent>
      </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" aria-hidden="true" />
            Thành viên
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : members.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Chưa có thành viên nào.
            </p>
          ) : (
            <ul className="divide-y">
              {members.map((member) => {
                const isSelf = member.user_id === currentUser?.id
                return (
                  <li
                    key={member.membership_id}
                    className="flex flex-wrap items-center gap-3 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {member.full_name || member.email}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {member.email}
                      </p>
                    </div>
                    {isCompanyAdmin &&
                    member.status === 'active' &&
                    !isSelf ? (
                      <Select
                        aria-label={`Vai trò của ${member.email}`}
                        value={member.role}
                        onChange={(event) =>
                          void handleRoleChange(
                            member,
                            event.target.value as MembershipRole,
                          )
                        }
                        className="h-8 w-36"
                      >
                        <option value="admin">Quản trị viên</option>
                        <option value="recruiter">Nhà tuyển dụng</option>
                        <option value="interviewer">Người phỏng vấn</option>
                      </Select>
                    ) : (
                      <Badge
                        variant={
                          member.role === 'admin' ? 'outline-ai' : 'neutral'
                        }
                      >
                        {MEMBERSHIP_ROLE_LABELS[member.role]}
                      </Badge>
                    )}
                    <Badge
                      variant={
                        member.status === 'active' ? 'success' : 'neutral'
                      }
                    >
                      {MEMBERSHIP_STATUS_LABELS[member.status]}
                    </Badge>
                    {isCompanyAdmin &&
                    member.status === 'active' &&
                    !isSelf ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => void handleRevokeMember(member)}
                      >
                        <UserMinus
                          className="h-4 w-4"
                          aria-hidden="true"
                        />
                        Thu hồi
                      </Button>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {isCompanyAdmin ? (
      <Card>
        <CardHeader>
          <CardTitle>Lời mời đã gửi</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-12 w-full" />
          ) : invitations.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Chưa có lời mời nào.
            </p>
          ) : (
            <ul className="divide-y">
              {invitations.map((invitation) => (
                <li
                  key={invitation.id}
                  className="flex flex-wrap items-center gap-3 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {invitation.email}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {MEMBERSHIP_ROLE_LABELS[invitation.role]}
                    </p>
                  </div>
                  <Badge
                    variant={
                      invitation.status === 'pending' ? 'outline-ai' : 'neutral'
                    }
                  >
                    {INVITATION_STATUS_LABELS[invitation.status]}
                  </Badge>
                  {invitation.status === 'pending' ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        void handleRevokeInvitation(invitation)
                      }
                    >
                      Thu hồi
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      ) : null}
    </div>
  )
}
