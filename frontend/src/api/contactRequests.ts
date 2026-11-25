import apiClient from '@/api/client'
import type {
  CandidateContactRequestRead,
  CandidateContactResponse,
  CandidatePreviewResponse,
  ContactRequestStatus,
  ContactRequestStatusCheck,
} from '@/types/ai'

/**
 * Fetch candidate preview for discovery (scrubbed PII).
 */
export async function getCandidatePreview(
  candidateId: string,
): Promise<CandidatePreviewResponse> {
  return apiClient.get<CandidatePreviewResponse, CandidatePreviewResponse>(
    `/ai/candidates/${candidateId}/preview`,
  )
}

/**
 * Recruiter sends contact authorization request to a discoverable candidate.
 */
export async function createContactRequest(
  candidateId: string,
): Promise<CandidateContactRequestRead> {
  return apiClient.post<
    CandidateContactRequestRead,
    CandidateContactRequestRead
  >('/contact-requests', { candidate_id: candidateId })
}

/**
 * List contact requests initiated by the active recruiter company.
 */
export async function getCompanyContactRequests(
  status?: ContactRequestStatus,
): Promise<CandidateContactRequestRead[]> {
  return apiClient.get<
    CandidateContactRequestRead[],
    CandidateContactRequestRead[]
  >('/contact-requests', {
    params: status ? { status } : undefined,
  })
}

/**
 * Check contact status and re-request eligibility for a candidate.
 */
export async function checkCandidateContactStatus(
  candidateId: string,
): Promise<ContactRequestStatusCheck> {
  return apiClient.get<
    ContactRequestStatusCheck,
    ContactRequestStatusCheck
  >(`/contact-requests/candidates/${candidateId}/status`)
}

/**
 * Dedicated authorized contact disclosure endpoint.
 * Returns email and phone when an accepted request exists.
 */
export async function getCandidateContactDetails(
  candidateId: string,
): Promise<CandidateContactResponse> {
  return apiClient.get<
    CandidateContactResponse,
    CandidateContactResponse
  >(`/contact-requests/candidates/${candidateId}/contact`)
}

/**
 * List incoming contact requests for the authenticated candidate.
 */
export async function getCandidateIncomingContactRequests(
  status?: ContactRequestStatus,
): Promise<CandidateContactRequestRead[]> {
  return apiClient.get<
    CandidateContactRequestRead[],
    CandidateContactRequestRead[]
  >('/candidate/contact-requests', {
    params: status ? { status } : undefined,
  })
}

/**
 * Candidate accepts an incoming contact request.
 */
export async function acceptContactRequest(
  requestId: string,
): Promise<CandidateContactRequestRead> {
  return apiClient.post<
    CandidateContactRequestRead,
    CandidateContactRequestRead
  >(`/candidate/contact-requests/${requestId}/accept`)
}

/**
 * Candidate declines an incoming contact request.
 */
export async function declineContactRequest(
  requestId: string,
): Promise<CandidateContactRequestRead> {
  return apiClient.post<
    CandidateContactRequestRead,
    CandidateContactRequestRead
  >(`/candidate/contact-requests/${requestId}/decline`)
}

/**
 * Candidate revokes a previously accepted contact authorization.
 */
export async function revokeContactAuthorization(
  requestId: string,
): Promise<CandidateContactRequestRead> {
  return apiClient.post<
    CandidateContactRequestRead,
    CandidateContactRequestRead
  >(`/candidate/contact-requests/${requestId}/revoke`)
}
