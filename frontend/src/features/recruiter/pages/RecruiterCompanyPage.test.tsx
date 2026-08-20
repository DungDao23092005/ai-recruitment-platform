import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { RecruiterCompanyPage } from './RecruiterCompanyPage'
import apiClient from '@/api/client'
import type { Company } from '@/types/company'

const mockCompany: Company = {
  id: 'company-1',
  name: 'TechNova AI',
  slug: 'technova-ai',
  tax_code: '0317654321',
  size: 'enterprise',
  created_at: '2026-01-10T00:00:00Z',
  updated_at: '2026-01-10T00:00:00Z',
}

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

const mockedGet = vi.mocked(apiClient.get)
const mockedPost = vi.mocked(apiClient.post)
const mockedPatch = vi.mocked(apiClient.patch)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RecruiterCompanyPage', () => {
  it('calls getCompanies() on mount', async () => {
    mockedGet.mockResolvedValue([] as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith('/companies')
    })
  })

  it('renders the company returned by getCompanies()', async () => {
    mockedGet.mockResolvedValue([mockCompany] as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
      expect(screen.getByText('@technova-ai')).toBeInTheDocument()
    })
    expect(screen.getByText('Mã số thuế: 0317654321')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Đăng tin tuyển dụng cho công ty này/i }),
    ).toHaveAttribute('href', '/recruiter/jobs/new')
    expect(screen.queryByText('Chưa có công ty')).not.toBeInTheDocument()
  })

  it('shows the existing empty state when there is no company', async () => {
    mockedGet.mockResolvedValue([] as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Chưa có công ty')).toBeInTheDocument()
    })
    expect(
      screen.queryByText('Đăng tin tuyển dụng cho công ty này'),
    ).not.toBeInTheDocument()
  })

  it('shows a friendly error when loading fails', async () => {
    const error = new Error('Network Error')
    Object.assign(error, {
      response: {
        status: 500,
        data: { detail: 'Không thể tải thông tin công ty.' },
      },
    })
    mockedGet.mockRejectedValueOnce(error)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Không thể tải thông tin công ty.',
      )
    })
    expect(screen.queryByText('Network Error')).not.toBeInTheDocument()
  })

  it('retries loading when the retry button is clicked', async () => {
    const error = new Error('Network Error')
    Object.assign(error, {
      response: {
        status: 500,
        data: { detail: 'Không thể tải thông tin công ty.' },
      },
    })
    mockedGet.mockRejectedValueOnce(error)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    mockedGet.mockResolvedValueOnce([mockCompany] as never)
    fireEvent.click(screen.getByRole('button', { name: /Thử lại/i }))

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledTimes(2)
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })
  })

  it('creates a company through the form', async () => {
    mockedGet.mockResolvedValue([] as never)
    mockedPost.mockResolvedValue(mockCompany as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Chưa có công ty')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Tên công ty'), {
      target: { value: 'TechNova AI' },
    })
    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'technova-ai' },
    })
    fireEvent.change(screen.getByLabelText('Mã số thuế'), {
      target: { value: '0317654321' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Tạo công ty' }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/companies', {
        name: 'TechNova AI',
        slug: 'technova-ai',
        tax_code: '0317654321',
        size: 'startup',
      })
      expect(
        screen.getByText('Tạo công ty thành công.'),
      ).toBeInTheDocument()
    })
  })

  it('onCreated immediately updates the company display without refetching', async () => {
    mockedGet.mockResolvedValue([] as never)
    mockedPost.mockResolvedValue(mockCompany as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledTimes(1)
    })

    fireEvent.change(screen.getByLabelText('Tên công ty'), {
      target: { value: 'TechNova AI' },
    })
    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'technova-ai' },
    })
    fireEvent.change(screen.getByLabelText('Mã số thuế'), {
      target: { value: '0317654321' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Tạo công ty' }))

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
      expect(
        screen.getByRole('link', {
          name: /Đăng tin tuyển dụng cho công ty này/i,
        }),
      ).toBeInTheDocument()
    })
    expect(mockedGet).toHaveBeenCalledTimes(1)
  })

  it('shows the edit button when a company exists', async () => {
    mockedGet.mockResolvedValue([mockCompany] as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Chỉnh sửa/i }),
    ).toBeInTheDocument()
  })

  it('does not show the edit button when there is no company', async () => {
    mockedGet.mockResolvedValue([] as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Chưa có công ty')).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('button', { name: /Chỉnh sửa/i }),
    ).not.toBeInTheDocument()
  })

  it('opens the prefilled edit form when edit is clicked', async () => {
    mockedGet.mockResolvedValue([mockCompany] as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Chỉnh sửa/i }))

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Chỉnh sửa công ty/i }),
      ).toBeInTheDocument()
    })
    expect(
      (screen.getByLabelText('Tên công ty') as HTMLInputElement).value,
    ).toBe('TechNova AI')
    expect(
      (screen.getByLabelText('Slug') as HTMLInputElement).value,
    ).toBe('technova-ai')
  })

  it('saves changes through patch and updates the display', async () => {
    mockedGet.mockResolvedValue([mockCompany] as never)
    const updated = {
      ...mockCompany,
      name: 'TechNova Renamed',
    }
    mockedPatch.mockResolvedValue(updated as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Chỉnh sửa/i }))

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Chỉnh sửa công ty/i }),
      ).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Tên công ty'), {
      target: { value: 'TechNova Renamed' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Lưu thay đổi/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith('/companies/company-1', {
        name: 'TechNova Renamed',
        slug: 'technova-ai',
        tax_code: '0317654321',
        size: 'enterprise',
      })
      expect(screen.getByText('TechNova Renamed')).toBeInTheDocument()
    })
    expect(
      screen.queryByRole('heading', { name: /Chỉnh sửa công ty/i }),
    ).not.toBeInTheDocument()
  })

  it('returns to the display when edit is cancelled', async () => {
    mockedGet.mockResolvedValue([mockCompany] as never)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Chỉnh sửa/i }))

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Chỉnh sửa công ty/i }),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Hủy chỉnh sửa/i }))

    await waitFor(() => {
      expect(
        screen.queryByRole('heading', { name: /Chỉnh sửa công ty/i }),
      ).not.toBeInTheDocument()
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })
  })

  it('shows a friendly error when the update fails', async () => {
    mockedGet.mockResolvedValue([mockCompany] as never)
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: {
        status: 400,
        data: { detail: 'Company with this tax code already exists' },
      },
    })
    mockedPatch.mockRejectedValue(error)

    render(
      <MemoryRouter>
        <RecruiterCompanyPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('TechNova AI')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Chỉnh sửa/i }))

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Chỉnh sửa công ty/i }),
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Lưu thay đổi/i }))

    await waitFor(() => {
      expect(
        screen.getByText('Mã số thuế đã được đăng ký. Vui lòng kiểm tra lại.'),
      ).toBeInTheDocument()
    })
  })
})