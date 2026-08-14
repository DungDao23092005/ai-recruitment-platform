import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ParsedResumeView } from './ParsedResumeView'
import type { ParsedResume } from '@/types/ai'

const mockResume: ParsedResume = {
  full_name: 'Jane Doe',
  email: 'jane@example.com',
  phone: '+84123456789',
  title: 'Data Scientist',
  summary: 'Machine learning specialist.',
  total_years_experience: 7,
  skills: ['Python', 'TensorFlow'],
  experiences: [
    {
      company: 'Tech Corp',
      position: 'Data Scientist',
      start_date: '2020-01-01',
      end_date: null,
      is_current: true,
      description: 'Built ML models.',
      skills_used: ['Python', 'ML'],
    },
  ],
  education: [
    {
      institution: 'University of Science',
      degree: 'Bachelor',
      field_of_study: 'Computer Science',
      start_year: 2013,
      end_year: 2017,
    },
  ],
  certifications: ['AWS Certified'],
  languages: ['English', 'Vietnamese'],
}

describe('ParsedResumeView', () => {
  it('renders the candidate name', () => {
    render(<ParsedResumeView resume={mockResume} />)
    expect(screen.getByText('Jane Doe')).toBeInTheDocument()
  })

  it('renders experience information', () => {
    render(<ParsedResumeView resume={mockResume} />)
    expect(screen.getByText('7 years experience')).toBeInTheDocument()
  })

  it('renders skills', () => {
    render(<ParsedResumeView resume={mockResume} />)
    expect(screen.getAllByText('Python').length).toBeGreaterThan(0)
    expect(screen.getByText('TensorFlow')).toBeInTheDocument()
  })

  it('renders experiences with position and company', () => {
    render(<ParsedResumeView resume={mockResume} />)
    expect(
      screen.getByText(/Data Scientist at Tech Corp/i),
    ).toBeInTheDocument()
  })

  it('renders education with institution and degree', () => {
    render(<ParsedResumeView resume={mockResume} />)
    expect(screen.getByText(/Bachelor in Computer Science/i)).toBeInTheDocument()
    expect(screen.getByText(/University of Science/)).toBeInTheDocument()
  })

  it('renders certifications and languages', () => {
    render(<ParsedResumeView resume={mockResume} />)
    expect(screen.getByText('AWS Certified')).toBeInTheDocument()
    expect(screen.getByText('English')).toBeInTheDocument()
  })

  it('handles null fields gracefully', () => {
    const emptyResume: ParsedResume = {
      full_name: null,
      email: null,
      phone: null,
      title: null,
      summary: null,
      total_years_experience: null,
      skills: [],
      experiences: [],
      education: [],
      certifications: [],
      languages: [],
    }

    render(<ParsedResumeView resume={emptyResume} />)
    expect(screen.getByText('Unnamed candidate')).toBeInTheDocument()
    expect(
      screen.getByText('No additional details were extracted from this resume.'),
    ).toBeInTheDocument()
  })
})