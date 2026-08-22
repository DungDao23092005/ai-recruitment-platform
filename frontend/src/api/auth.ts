import apiClient from '@/api/client'
import type {
  CandidateProfile,
  CandidateProfileData,
  CandidateProfileRead,
  CandidateProfileUpdate,
  LoginCredentials,
  RecruiterProfile,
  RecruiterProfileData,
  RegisterData,
  Token,
  User,
} from '@/types/auth'

export async function login(
  credentials: LoginCredentials,
): Promise<Token> {
  return apiClient.post<Token, Token>('/auth/login/json', credentials)
}

export async function register(data: RegisterData): Promise<User> {
  return apiClient.post<User, User>('/auth/register', data)
}

export async function getCurrentUser(): Promise<User> {
  return apiClient.get<User, User>('/auth/me')
}

export async function forgotPassword(email: string): Promise<{ message: string }> {
  return apiClient.post<{ message: string }, { message: string }>('/auth/forgot-password', { email })
}

export async function verifyResetOtp(email: string, otp: string): Promise<{ reset_token: string }> {
  return apiClient.post<{ reset_token: string }, { reset_token: string }>('/auth/verify-reset-otp', { email, otp })
}

export async function resetPassword(email: string, reset_token: string, new_password: string): Promise<{ message: string }> {
  return apiClient.post<{ message: string }, { message: string }>('/auth/reset-password', { email, reset_token, new_password, confirm_password: new_password })
}

export async function createCandidateProfile(
  data: CandidateProfileData,
): Promise<CandidateProfile> {
  return apiClient.post<CandidateProfile, CandidateProfile>(
    '/users/me/candidate-profile',
    data,
  )
}

export async function getCandidateProfile(): Promise<CandidateProfileRead> {
  return apiClient.get<CandidateProfileRead, CandidateProfileRead>(
    '/users/me/candidate-profile',
  )
}

export async function updateCandidateProfile(
  data: CandidateProfileUpdate,
): Promise<CandidateProfileRead> {
  return apiClient.put<CandidateProfileRead, CandidateProfileRead>(
    '/users/me/candidate-profile',
    data,
  )
}

export async function createRecruiterProfile(
  data: RecruiterProfileData,
): Promise<RecruiterProfile> {
  return apiClient.post<RecruiterProfile, RecruiterProfile>(
    '/users/me/recruiter-profile',
    data,
  )
}

export async function getRecruiterProfile(): Promise<RecruiterProfile> {
  return apiClient.get<RecruiterProfile, RecruiterProfile>(
    '/users/me/recruiter-profile',
  )
}

export async function updateRecruiterProfile(
  data: RecruiterProfileData,
): Promise<RecruiterProfile> {
  return apiClient.put<RecruiterProfile, RecruiterProfile>(
    '/users/me/recruiter-profile',
    data,
  )
}