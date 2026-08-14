import apiClient from '@/api/client'
import type {
  CandidateProfile,
  CandidateProfileData,
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

export async function createCandidateProfile(
  data: CandidateProfileData,
): Promise<CandidateProfile> {
  return apiClient.post<CandidateProfile, CandidateProfile>(
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