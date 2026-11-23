import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Briefcase, CalendarCheck, CheckCircle2, Info, MailPlus, Send, ShieldCheck, UserMinus, Users } from 'lucide-react'
import { cn } from '@/utils/cn'
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
import { Modal } from '@/components/ui/modal'
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

const ROLE_OPTIONS: {
  value: MembershipRole
  label: string
  description: string
  icon: typeof Briefcase
}[] = [
  {
    value: 'recruiter',
    label: 'Nhà tuyển dụng',
    description:
      'Đăng tin tuyển dụng, quản lý hồ sơ ứng viên và điều phối tuyển dụng.',
    icon: Briefcase,
  },
  {
    value: 'interviewer',
    label: 'Người phỏng vấn',
    description: 'Xem lịch phỏng vấn được phân công và đánh giá ứng viên.',
    icon: CalendarCheck,
  },
  {
    value: 'admin',
    label: 'Quản trị viên',
    description:
      'Quản trị không gian làm việc, mời thành viên và quản lý gói dịch vụ.',
    icon: ShieldCheck,
  },
]

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
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [inviteSuccessMessage, setInviteSuccessMessage] = useState<string | null>(null)

  const [memberToRevoke, setMemberToRevoke] = useState<WorkspaceMember | null>(null)
  const [isRevokingMember, setIsRevokingMember] = useState(false)
  const [revokeMemberError, setRevokeMemberError] = useState<string | null>(null)

  const [invitationToRevoke, setInvitationToRevoke] = useState<WorkspaceInvitation | null>(null)
  const [isRevokingInvitation, setIsRevokingInvitation] = useState(false)
  const [revokeInvitationError, setRevokeInvitationError] = useState<string | null>(null)

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
    setInviteError(null)
    setInviteSuccessMessage(null)
    setIsInviting(true)
    try {
      await createWorkspaceInvitation({ email: email.trim(), role })
      setEmail('')
      setInviteSuccessMessage('Đã gửi lời mời tham gia công ty.')
      await loadWorkspaceData()
    } catch (inviteErr) {
      setInviteError(getFriendlyErrorMessage(inviteErr))
    } finally {
      setIsInviting(false)
    }
  }

  const handleRoleKeyDown = (
    event: React.KeyboardEvent,
    currentIndex: number,
  ) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      event.preventDefault()
      const nextIndex = (currentIndex + 1) % ROLE_OPTIONS.length
      setRole(ROLE_OPTIONS[nextIndex].value)
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      event.preventDefault()
      const prevIndex =
        (currentIndex - 1 + ROLE_OPTIONS.length) % ROLE_OPTIONS.length
      setRole(ROLE_OPTIONS[prevIndex].value)
    } else if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault()
      setRole(ROLE_OPTIONS[currentIndex].value)
    }
  }

  const handleOpenRevokeMemberModal = (member: WorkspaceMember) => {
    setRevokeMemberError(null)
    setMemberToRevoke(member)
  }

  const handleCloseRevokeMemberModal = () => {
    if (isRevokingMember) return
    setMemberToRevoke(null)
    setRevokeMemberError(null)
  }

  const handleConfirmRevokeMember = async () => {
    if (!memberToRevoke || isRevokingMember) return
    setIsRevokingMember(true)
    setRevokeMemberError(null)
    try {
      await revokeWorkspaceMember(memberToRevoke.membership_id)
      setMemberToRevoke(null)
      await loadWorkspaceData()
      await refreshWorkspaces()
    } catch (revokeError) {
      setRevokeMemberError(getFriendlyErrorMessage(revokeError))
    } finally {
      setIsRevokingMember(false)
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

  const handleOpenRevokeInvitationModal = (invitation: WorkspaceInvitation) => {
    setRevokeInvitationError(null)
    setInvitationToRevoke(invitation)
  }

  const handleCloseRevokeInvitationModal = () => {
    if (isRevokingInvitation) return
    setInvitationToRevoke(null)
    setRevokeInvitationError(null)
  }

  const handleConfirmRevokeInvitation = async () => {
    if (!invitationToRevoke || isRevokingInvitation) return
    setIsRevokingInvitation(true)
    setRevokeInvitationError(null)
    try {
      await revokeWorkspaceInvitation(invitationToRevoke.id)
      setInvitationToRevoke(null)
      await loadWorkspaceData()
    } catch (revokeError) {
      setRevokeInvitationError(getFriendlyErrorMessage(revokeError))
    } finally {
      setIsRevokingInvitation(false)
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
        <Card className="shadow-soft">
          <CardHeader className="flex flex-row items-start gap-4 space-y-0">
            <div className="rounded-full bg-primary/10 p-2.5 text-primary">
              <MailPlus className="h-6 w-6" aria-hidden="true" />
            </div>
            <div className="space-y-1">
              <CardTitle className="text-xl">Mời thành viên mới</CardTitle>
              <CardDescription>
                Gửi lời mời tham gia không gian làm việc của công ty qua email.
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {inviteError ? (
              <div
                role="alert"
                className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {inviteError}
              </div>
            ) : null}
            {inviteSuccessMessage ? (
              <p
                role="status"
                className="rounded-md bg-success/10 px-3 py-2 text-sm font-medium text-success"
              >
                {inviteSuccessMessage}
              </p>
            ) : null}

            <form onSubmit={handleInvite} className="space-y-6">
              <div className="space-y-2">
                <Input
                  type="email"
                  name="invite-email"
                  label="Địa chỉ email đồng nghiệp"
                  placeholder="dongnghiep@company.com"
                  helperText="Chỉ có thể mời đồng nghiệp đã có tài khoản trên hệ thống."
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </div>

              <div className="space-y-3">
                <label className="text-sm font-medium text-foreground">
                  Vai trò
                </label>
                <div
                  role="radiogroup"
                  aria-label="Chọn vai trò thành viên"
                  className="grid grid-cols-1 md:grid-cols-3 gap-4"
                >
                  {ROLE_OPTIONS.map((option, index) => {
                    const isSelected = role === option.value
                    const IconComponent = option.icon
                    return (
                      <div
                        key={option.value}
                        role="radio"
                        aria-checked={isSelected}
                        tabIndex={isSelected ? 0 : -1}
                        onClick={() => setRole(option.value)}
                        onKeyDown={(e) => handleRoleKeyDown(e, index)}
                        className={cn(
                          'relative flex cursor-pointer flex-col justify-between rounded-xl border p-4 text-left transition-all duration-150 outline-none',
                          'focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                          isSelected
                            ? 'border-primary bg-primary/5 ring-2 ring-primary/20 shadow-soft'
                            : 'border-border bg-card hover:border-primary/40 hover:bg-muted/30',
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2.5">
                            <div
                              className={cn(
                                'rounded-lg p-2 transition-colors',
                                isSelected
                                  ? 'bg-primary text-primary-foreground'
                                  : 'bg-muted text-muted-foreground',
                              )}
                            >
                              <IconComponent className="h-5 w-5" aria-hidden="true" />
                            </div>
                            <span className="font-semibold text-sm text-foreground">
                              {option.label}
                            </span>
                          </div>
                          {isSelected ? (
                            <CheckCircle2
                              className="h-5 w-5 text-primary shrink-0"
                              aria-hidden="true"
                            />
                          ) : (
                            <div
                              className="h-5 w-5 rounded-full border border-muted-foreground/30 shrink-0"
                              aria-hidden="true"
                            />
                          )}
                        </div>
                        <p className="mt-3 text-xs text-muted-foreground leading-relaxed">
                          {option.description}
                        </p>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="flex items-start gap-2.5 rounded-lg border border-border/60 bg-muted/30 p-3 text-xs text-muted-foreground">
                <Info className="h-4 w-4 shrink-0 text-primary mt-0.5" aria-hidden="true" />
                <p>
                  Lời mời có thời hạn 7 ngày và chỉ dùng được một lần. Người được mời cần có tài khoản hợp lệ trong hệ thống để tham gia công ty.
                </p>
              </div>

              <div className="flex justify-end">
                <Button
                  type="submit"
                  isLoading={isInviting}
                  disabled={isInviting}
                  className="w-full sm:w-auto"
                >
                  <Send className="mr-2 h-4 w-4" aria-hidden="true" />
                  Gửi lời mời tham gia
                </Button>
              </div>
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
                        onClick={() => handleOpenRevokeMemberModal(member)}
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
                        handleOpenRevokeInvitationModal(invitation)
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

      {memberToRevoke ? (
        <Modal
          onClose={handleCloseRevokeMemberModal}
          size="sm"
          ariaLabel="Thu hồi quyền truy cập thành viên"
          title="Thu hồi quyền truy cập thành viên"
          description="Thành viên này sẽ mất quyền truy cập vào không gian làm việc của công ty."
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                onClick={handleCloseRevokeMemberModal}
                disabled={isRevokingMember}
              >
                Hủy
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={handleConfirmRevokeMember}
                isLoading={isRevokingMember}
                disabled={isRevokingMember}
              >
                Thu hồi quyền truy cập
              </Button>
            </>
          }
        >
          <div className="space-y-3">
            {revokeMemberError ? (
              <div
                role="alert"
                className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {revokeMemberError}
              </div>
            ) : null}
            <div className="rounded-lg border bg-muted/30 p-3 text-sm space-y-1">
              <p>
                <span className="text-muted-foreground">Thành viên: </span>
                <span className="font-medium text-foreground">
                  {memberToRevoke.full_name || memberToRevoke.email}
                </span>
              </p>
              <p>
                <span className="text-muted-foreground">Email: </span>
                <span className="font-medium text-foreground">
                  {memberToRevoke.email}
                </span>
              </p>
              <p>
                <span className="text-muted-foreground">Vai trò: </span>
                <span className="font-medium text-foreground">
                  {MEMBERSHIP_ROLE_LABELS[memberToRevoke.role]}
                </span>
              </p>
            </div>
          </div>
        </Modal>
      ) : null}

      {invitationToRevoke ? (
        <Modal
          onClose={handleCloseRevokeInvitationModal}
          size="sm"
          ariaLabel="Thu hồi lời mời tham gia"
          title="Thu hồi lời mời tham gia"
          description="Người nhận sẽ không thể sử dụng lời mời này để tham gia công ty nữa."
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                onClick={handleCloseRevokeInvitationModal}
                disabled={isRevokingInvitation}
              >
                Hủy
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={handleConfirmRevokeInvitation}
                isLoading={isRevokingInvitation}
                disabled={isRevokingInvitation}
              >
                Thu hồi lời mời
              </Button>
            </>
          }
        >
          <div className="space-y-3">
            {revokeInvitationError ? (
              <div
                role="alert"
                className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {revokeInvitationError}
              </div>
            ) : null}
            <div className="rounded-lg border bg-muted/30 p-3 text-sm space-y-1">
              <p>
                <span className="text-muted-foreground">Email người nhận: </span>
                <span className="font-medium text-foreground">
                  {invitationToRevoke.email}
                </span>
              </p>
              <p>
                <span className="text-muted-foreground">Vai trò: </span>
                <span className="font-medium text-foreground">
                  {MEMBERSHIP_ROLE_LABELS[invitationToRevoke.role]}
                </span>
              </p>
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
