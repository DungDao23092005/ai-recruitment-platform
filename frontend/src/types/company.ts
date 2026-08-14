export type CompanySize = 'seed' | 'startup' | 'sme' | 'enterprise'

export interface Company {
  id: string
  name: string
  slug: string
  tax_code: string
  size: CompanySize
  created_at: string
  updated_at: string
}

export interface CompanyCreateData {
  name: string
  slug: string
  tax_code: string
  size: CompanySize
}

export const COMPANY_SIZE_LABELS: Record<CompanySize, string> = {
  seed: 'Seed',
  startup: 'Startup',
  sme: 'SME',
  enterprise: 'Enterprise',
}

export const COMPANY_SIZES: CompanySize[] = [
  'seed',
  'startup',
  'sme',
  'enterprise',
]
