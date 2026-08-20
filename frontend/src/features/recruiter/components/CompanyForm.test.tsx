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
  updateCompany: vi.fn(),
  getCompanyById: vi.fn(),
}))

const mockedCreateCompany = vi.mocked(companiesApi.createCompany)
const mockedUpdateCompany = vi.mocked(companiesApi.updateCompany)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CompanyForm', () => {
  it('requires company name', async () => {
    render(<CompanyForm />)

    fireEvent.click(screen.getByRole('button', { name: /Tạo công ty/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Tên công ty là bắt buộc'),
      ).toBeInTheDocument()
    })
    expect(mockedCreateCompany).not.toHaveBeenCalled()
  })

  it('requires tax code', async () => {
    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText('Tên công ty'), {
      target: { value: 'Acme Corporation' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo công ty/i }))

    await waitFor(() => {
      expect(screen.getByText('Mã số thuế là bắt buộc')).toBeInTheDocument()
    })
    expect(mockedCreateCompany).not.toHaveBeenCalled()
  })

  it('allows selecting company size', () => {
    render(<CompanyForm />)

    const sizeSelect = screen.getByLabelText('Quy mô công ty')
    fireEvent.change(sizeSelect, { target: { value: 'enterprise' } })

    expect((sizeSelect as HTMLSelectElement).value).toBe('enterprise')
  })

  it('creates a company on submit', async () => {
    mockedCreateCompany.mockResolvedValue(mockCompany)

    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText('Tên công ty'), {
      target: { value: 'Acme Corporation' },
    })
    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'acme-corporation' },
    })
    fireEvent.change(screen.getByLabelText('Mã số thuế'), {
      target: { value: '0312345678' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo công ty/i }))

    await waitFor(() => {
      expect(mockedCreateCompany).toHaveBeenCalledWith({
        name: 'Acme Corporation',
        slug: 'acme-corporation',
        tax_code: '0312345678',
        size: 'startup',
      })
      expect(
        screen.getByText('Tạo công ty thành công.'),
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

    fireEvent.change(screen.getByLabelText('Tên công ty'), {
      target: { value: 'Acme Corporation' },
    })
    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'acme-corporation' },
    })
    fireEvent.change(screen.getByLabelText('Mã số thuế'), {
      target: { value: '0312345678' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo công ty/i }))

    await waitFor(() => {
      expect(
        screen.getByText(
          'Mã số thuế đã được đăng ký. Vui lòng kiểm tra lại.',
        ),
      ).toBeInTheDocument()
    })
  })

  it('calls onCreated with the created company', async () => {
    mockedCreateCompany.mockResolvedValue(mockCompany)
    const onCreated = vi.fn()

    render(<CompanyForm onCreated={onCreated} />)

    fireEvent.change(screen.getByLabelText('Tên công ty'), {
      target: { value: 'Acme Corporation' },
    })
    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'acme-corporation' },
    })
    fireEvent.change(screen.getByLabelText('Mã số thuế'), {
      target: { value: '0312345678' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Tạo công ty/i }))

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(mockCompany)
    })
  })
})

describe('CompanyForm edit mode', () => {
  it('prefills fields from the company', () => {
    render(<CompanyForm mode="edit" company={mockCompany} />)

    expect(
      (screen.getByLabelText('Tên công ty') as HTMLInputElement).value,
    ).toBe('Acme Corporation')
    expect(
      (screen.getByLabelText('Slug') as HTMLInputElement).value,
    ).toBe('acme-corporation')
    expect(
      (screen.getByLabelText('Mã số thuế') as HTMLInputElement).value,
    ).toBe('0312345678')
    expect(
      (screen.getByLabelText('Quy mô công ty') as HTMLSelectElement).value,
    ).toBe('startup')
  })

  it('updates the company on submit', async () => {
    mockedUpdateCompany.mockResolvedValue({
      ...mockCompany,
      name: 'Renamed Corp',
    })
    const onUpdated = vi.fn()

    render(<CompanyForm mode="edit" company={mockCompany} onUpdated={onUpdated} />)

    fireEvent.change(screen.getByLabelText('Tên công ty'), {
      target: { value: 'Renamed Corp' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Lưu thay đổi/i }))

    await waitFor(() => {
      expect(mockedUpdateCompany).toHaveBeenCalledWith('company-1', {
        name: 'Renamed Corp',
        slug: 'acme-corporation',
        tax_code: '0312345678',
        size: 'startup',
      })
      expect(
        screen.getByText('Cập nhật công ty thành công.'),
      ).toBeInTheDocument()
      expect(onUpdated).toHaveBeenCalledWith({
        ...mockCompany,
        name: 'Renamed Corp',
      })
    })
  })

  it('shows the cancel button in edit mode', () => {
    const onCancelEdit = vi.fn()
    render(
      <CompanyForm
        mode="edit"
        company={mockCompany}
        onCancelEdit={onCancelEdit}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Hủy chỉnh sửa/i }))
    expect(onCancelEdit).toHaveBeenCalled()
  })

  it('does not show a cancel button in create mode', () => {
    render(<CompanyForm />)
    expect(
      screen.queryByRole('button', { name: /Hủy chỉnh sửa/i }),
    ).not.toBeInTheDocument()
  })

  it('does not call createCompany in edit mode', async () => {
    mockedUpdateCompany.mockResolvedValue(mockCompany)

    render(<CompanyForm mode="edit" company={mockCompany} />)

    fireEvent.click(screen.getByRole('button', { name: /Lưu thay đổi/i }))

    await waitFor(() => {
      expect(mockedCreateCompany).not.toHaveBeenCalled()
    })
  })
})