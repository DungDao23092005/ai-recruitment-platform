export interface WorkExperience {
  company: string | null
  position: string | null
  start_date: string | null
  end_date: string | null
  is_current: boolean
  description: string | null
  skills_used: string[]
}

export interface Education {
  institution: string | null
  degree: string | null
  field_of_study: string | null
  start_year: number | null
  end_year: number | null
}

export interface ParsedResume {
  full_name: string | null
  email: string | null
  phone: string | null
  title: string | null
  summary: string | null
  total_years_experience: number | null
  skills: string[]
  experiences: WorkExperience[]
  education: Education[]
  certifications: string[]
  languages: string[]
}