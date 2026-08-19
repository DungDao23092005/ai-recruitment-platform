import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { AdminCompaniesPage } from './AdminCompaniesPage'
import * as adminApi from '@/api/admin'
import type { AdminCompany, AdminCompanyList } from '@/types/admin'

function makeCompany(overrides: Partial<AdminCompany> = {}): AdminCompany {
  return {
    id: 'company-1',
    name: 'Acme Corp',
    slug: 'acme-corp',
    tax_code: '1234567890',
    size: 'sme',
    is_deleted: false,
    created_at: '2026-01-10T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
    ...overrides,
  }
}

const active = makeCompany()
const startup = makeCompany({
  id: 'company-2',
  name: 'Globex',
  slug: 'globex',
  tax_code: '0987654321',
  size: 'startup',
})
const locked = makeCompany({
  id: 'company-3',
  name: 'Initech',
  slug: 'initech',
  tax_code: '5555555555',
  size: 'enterprise',
  is_deleted: true,
})

function makeList(
  items: AdminCompany[] = [active, startup, locked],
  total = items.length,
): AdminCompanyList {
  return { items, total, skip: 0, limit: 10 }
}

vi.mock('@/api/admin', () => ({
  getAdminStats: vi.fn(),
  getSystemHealth: vi.fn(),
  getAdminUsers: vi.fn(),
  getAdminUserById: vi.fn(),
  deactivateAdminUser: vi.fn(),
  getAdminCompanies: vi.fn(),
  deleteAdminCompany: vi.fn(),
}))

const mockedGetAdminCompanies = vi.mocked(adminApi.getAdminCompanies)
const mockedDeleteAdminCompany = vi.mocked(adminApi.deleteAdminCompany)

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminCompaniesPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedGetAdminCompanies.mockResolvedValue(makeList())
})

describe('AdminCompaniesPage', () => {
  it('fetches companies on mount with default pagination', async () => {
    renderPage()

    await waitFor(() => {
      expect(mockedGetAdminCompanies).toHaveBeenCalledWith({
        skip: 0,
        limit: 10,
        search: undefined,
      })
    })
  })

  it('renders companies with size and status badges', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
      expect(screen.getByText('Globex')).toBeInTheDocument()
    })
    const table = screen.getByRole('table')
    expect(within(table).getAllByText('SME').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Startup').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Doanh nghiệp lớn').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Đang hoạt động')).toHaveLength(2)
    expect(within(table).getByText('Đã khóa')).toBeInTheDocument()
  })

  it('renders company identifiers', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('acme-corp')).toBeInTheDocument()
      expect(screen.getByText('1234567890')).toBeInTheDocument()
    })
  })

  it('renders the empty state when no companies match', async () => {
    mockedGetAdminCompanies.mockResolvedValue(makeList([], 0))

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText('Không tìm thấy công ty'),
      ).toBeInTheDocument()
    })
  })

  it('shows an error state with retry', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedGetAdminCompanies
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(makeList())

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })
  })

  it('searches on submit and resets to page one', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })

    fireEvent.change(
      screen.getByLabelText('Tìm theo tên, slug hoặc mã số thuế'),
      { target: { value: 'acme' } },
    )
    fireEvent.click(screen.getByRole('button', { name: 'Tìm kiếm' }))

    await waitFor(() => {
      expect(mockedGetAdminCompanies).toHaveBeenLastCalledWith({
        skip: 0,
        limit: 10,
        search: 'acme',
      })
    })
  })

  it('paginates to the next page with the correct skip', async () => {
    const manyCompanies = Array.from({ length: 12 }, (_, index) =>
      makeCompany({
        id: `company-${index}`,
        name: `Company ${index}`,
      }),
    )
    mockedGetAdminCompanies.mockResolvedValue(
      makeList(manyCompanies.slice(0, 10), manyCompanies.length),
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Trang 1 / 2')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))

    await waitFor(() => {
      expect(mockedGetAdminCompanies).toHaveBeenLastCalledWith({
        skip: 10,
        limit: 10,
        search: undefined,
      })
    })
    expect(screen.getByText('Trang 2 / 2')).toBeInTheDocument()
  })

  it('disables the lock action for a locked company', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Initech')).toBeInTheDocument()
    })

    expect(
      screen.getByRole('button', { name: 'Khóa công ty Initech' }),
    ).toBeDisabled()
  })

  it('locks a company after confirmation and reloads the list', async () => {
    mockedDeleteAdminCompany.mockResolvedValue()

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: 'Khóa công ty Acme Corp' }),
    )

    expect(
      screen.getByRole('dialog', { name: 'Khóa công ty' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/bị vô hiệu hóa/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/được gỡ khỏi cơ sở dữ liệu AI/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/được giữ nguyên và không bị xóa/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Khóa công ty' }))

    await waitFor(() => {
      expect(mockedDeleteAdminCompany).toHaveBeenCalledWith('company-1')
    })

    await waitFor(() => {
      expect(mockedGetAdminCompanies).toHaveBeenCalledTimes(2)
    })
  })

  it('shows an error inside the lock dialog when locking fails', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 500, data: { detail: 'Server error' } },
    })
    mockedDeleteAdminCompany.mockRejectedValue(error)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: 'Khóa công ty Acme Corp' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Khóa công ty' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Server error')
    })
    expect(
      screen.getByRole('dialog', { name: 'Khóa công ty' }),
    ).toBeInTheDocument()
  })

  it('closes the lock dialog without reloading', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })

    fireEvent.click(
      screen.getByRole('button', { name: 'Khóa công ty Acme Corp' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Hủy' }))

    await waitFor(() => {
      expect(
        screen.queryByRole('dialog', { name: 'Khóa công ty' }),
      ).not.toBeInTheDocument()
    })
    expect(mockedGetAdminCompanies).toHaveBeenCalledTimes(1)
  })
})