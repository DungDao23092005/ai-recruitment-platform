import apiClient from '@/api/client'
import type { Company, CompanyCreateData } from '@/types/company'

export async function createCompany(data: CompanyCreateData): Promise<Company> {
  return apiClient.post<Company, Company>('/companies', data)
}

export async function getCompanyById(id: string): Promise<Company> {
  return apiClient.get<Company, Company>(`/companies/${id}`)
}

export async function getCompanies(): Promise<Company[]> {
  return apiClient.get<Company[], Company[]>('/companies')
}
