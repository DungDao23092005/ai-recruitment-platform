import apiClient from '@/api/client'
import type {
  InvitationAcceptResult,
  InvitationPreview,
  MembershipRole,
  Workspace,
  WorkspaceInvitation,
  WorkspaceMember,
} from '@/types/workspace'

export async function getWorkspaces(): Promise<Workspace[]> {
  return apiClient.get<Workspace[], Workspace[]>('/workspaces')
}

export async function getWorkspaceMembers(): Promise<WorkspaceMember[]> {
  return apiClient.get<WorkspaceMember[], WorkspaceMember[]>(
    '/workspaces/members',
  )
}

export async function updateWorkspaceMemberRole(
  membershipId: string,
  role: MembershipRole,
): Promise<WorkspaceMember> {
  return apiClient.patch<WorkspaceMember, WorkspaceMember>(
    `/workspaces/members/${membershipId}/role`,
    { role },
  )
}

export async function revokeWorkspaceMember(
  membershipId: string,
): Promise<void> {
  await apiClient.delete(`/workspaces/members/${membershipId}`)
}

export async function getWorkspaceInvitations(): Promise<
  WorkspaceInvitation[]
> {
  return apiClient.get<WorkspaceInvitation[], WorkspaceInvitation[]>(
    '/workspaces/invitations',
  )
}

export async function createWorkspaceInvitation(data: {
  email: string
  role: MembershipRole
}): Promise<WorkspaceInvitation> {
  return apiClient.post<WorkspaceInvitation, WorkspaceInvitation>(
    '/workspaces/invitations',
    data,
  )
}

export async function revokeWorkspaceInvitation(
  invitationId: string,
): Promise<WorkspaceInvitation> {
  return apiClient.post<WorkspaceInvitation, WorkspaceInvitation>(
    `/workspaces/invitations/${invitationId}/revoke`,
  )
}

export async function previewInvitation(
  token: string,
): Promise<InvitationPreview> {
  return apiClient.post<InvitationPreview, InvitationPreview>(
    '/invitations/preview',
    { token },
  )
}

export async function acceptInvitation(
  token: string,
): Promise<InvitationAcceptResult> {
  return apiClient.post<InvitationAcceptResult, InvitationAcceptResult>(
    '/invitations/accept',
    { token },
  )
}
