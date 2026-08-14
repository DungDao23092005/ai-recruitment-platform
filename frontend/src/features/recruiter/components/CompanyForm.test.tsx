import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { CompanyForm } from './CompanyForm'
import * as companiesApi from '@/api/companies'
import type { Company } from '@/types/company'

const mockCompany: Company = {
  id: 'company-1',
  name: 'Acme Corporation',
  slug: 'acme-corporation',
  tax_code: '0312345678',
  size: 'startup',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
}

vi.mock('@/api/companies', () => ({
  createCompany: vi.fn(),
  getCompanyById: vi.fn(),
}))

const mockedCreateCompany = vi.mocked(companiesApi.createCompany)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CompanyForm', () => {
  it('requires company name', async () => {
    render(<CompanyForm />)

    fireEvent.click(screen.getByRole('button', { name: /Create company/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Company name is required'),
      ).toBeInTheDocument()
    })
    expect(mockedCreateCompany).not.toHaveBeenCalled()
  })

  it('requires tax code', async () => {
    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText('Company name'), {
      target: { value: 'Acme Corporation' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Create company/i }))

    await waitFor(() => {
      expect(screen.getByText('Tax code is required')).toBeInTheDocument()
    })
    expect(mockedCreateCompany).not.toHaveBeenCalled()
  })

  it('allows selecting company size', () => {
    render(<CompanyForm />)

    const sizeSelect = screen.getByLabelText('Company size')
    fireEvent.change(sizeSelect, { target: { value: 'enterprise' } })

    expect((sizeSelect as HTMLSelectElement).value).toBe('enterprise')
  })

  it('creates a company on submit', async () => {
    mockedCreateCompany.mockResolvedValue(mockCompany)

    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText('Company name'), {
      target: { value: 'Acme Corporation' },
    })
    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'acme-corporation' },
    })
    fireEvent.change(screen.getByLabelText('Tax code'), {
      target: { value: '0312345678' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Create company/i }))

    await waitFor(() => {
      expect(mockedCreateCompany).toHaveBeenCalledWith({
        name: 'Acme Corporation',
        slug: 'acme-corporation',
        tax_code: '0312345678',
        size: 'startup',
      })
      expect(
        screen.getByText('Company created successfully.'),
      ).toBeInTheDocument()
    })
  })

  it('shows friendly error for duplicate tax code', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: {
        status: 400,
        data: { detail: 'Company with this tax code already exists' },
      },
    })
    mockedCreateCompany.mockRejectedValue(error)

    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText('Company name'), {
      target: { value: 'Acme Corporation' },
    })
    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'acme-corporation' },
    })
    fireEvent.change(screen.getByLabelText('Tax code'), {
      target: { value: '0312345678' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Create company/i }))

    await waitFor(() => {
      expect(
        screen.getByText(
          'Tax code already registered. Please check and try again.',
        ),
      ).toBeInTheDocument()
    })
  })

  it('calls onCreated with the created company', async () => {
    mockedCreateCompany.mockResolvedValue(mockCompany)
    const onCreated = vi.fn()

    render(<CompanyForm onCreated={onCreated} />)

    fireEvent.change(screen.getByLabelText('Company name'), {
      target: { value: 'Acme Corporation' },
    })
    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'acme-corporation' },
    })
    fireEvent.change(screen.getByLabelText('Tax code'), {
      target: { value: '0312345678' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Create company/i }))

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(mockCompany)
    })
  })
})