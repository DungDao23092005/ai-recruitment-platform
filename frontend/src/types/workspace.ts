export type MembershipRole = 'admin' | 'recruiter' | 'interviewer'
export type MembershipStatus = 'active' | 'revoked'
export type InvitationStatus =
  | 'pending'
  | 'accepted'
  | 'declined'
  | 'revoked'
  | 'expired'

export interface Workspace {
  company_id: string
  company_name: string
  company_slug: string
  membership_id: string | null
  role: MembershipRole | null
  is_platform_admin: boolean
}

export interface WorkspaceMember {
  membership_id: string
  user_id: string
  email: string
  full_name: string | null
  role: MembershipRole
  status: MembershipStatus
  joined_at: string | null
  revoked_at: string | null
}

export interface WorkspaceInvitation {
  id: string
  company_id: string
  email: string
  role: MembershipRole
  status: InvitationStatus
  expires_at: string
  accepted_at: string | null
  revoked_at: string | null
  created_at: string
  updated_at: string
}

export interface InvitationPreview {
  company_name: string
  company_slug: string
  email_masked: string
  role: MembershipRole
  status: InvitationStatus
  expires_at: string
  can_accept: boolean
}

export interface InvitationAcceptResult {
  workspace: Workspace
  membership_id: string
}

export const MEMBERSHIP_ROLE_LABELS: Record<MembershipRole, string> = {
  admin: 'Quản trị viên',
  recruiter: 'Nhà tuyển dụng',
  interviewer: 'Người phỏng vấn',
}

export const MEMBERSHIP_STATUS_LABELS: Record<MembershipStatus, string> = {
  active: 'Đang hoạt động',
  revoked: 'Đã thu hồi',
}

export const INVITATION_STATUS_LABELS: Record<InvitationStatus, string> = {
  pending: 'Đang chờ',
  accepted: 'Đã chấp nhận',
  declined: 'Đã từ chối',
  revoked: 'Đã thu hồi',
  expired: 'Đã hết hạn',
}

export interface MyInvitation {
  id: string
  company_id: string
  company_name: string
  company_slug: string
  role: MembershipRole
  status: InvitationStatus
  expires_at: string
  created_at: string
  can_accept: boolean
  can_decline: boolean
}

export interface InvitationDeclineResult {
  invitation_id: string
  status: InvitationStatus
}
