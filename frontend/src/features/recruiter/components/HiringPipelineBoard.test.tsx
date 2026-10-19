import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { HiringPipelineBoard } from './HiringPipelineBoard'
import * as applicationsApi from '@/api/applications'
import type { Application, ApplicationStatus } from '@/types/application'

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

vi.mock('@/api/applications', () => ({
  getApplicationDetail: vi.fn(),
  getApplicationMatch: vi.fn(),
}))

const mockedGetApplicationDetail = vi.mocked(
  applicationsApi.getApplicationDetail,
)

function makeApplication(
  id: string,
  candidateId: string,
  status: ApplicationStatus,
): Application {
  return {
    id,
    candidate_id: candidateId,
    job_id: 'job-1',
    status,
    created_at: '2026-01-20T00:00:00Z',
    updated_at: '2026-01-20T00:00:00Z',
    candidate: null,
  }
}

const applications: Application[] = [
  makeApplication('app-1', '11111111-1111-1111-1111-111111111111', 'applied'),
  makeApplication(
    'app-2',
    '22222222-2222-2222-2222-222222222222',
    'shortlisted',
  ),
  makeApplication(
    'app-3',
    '33333333-3333-3333-3333-333333333333',
    'offered',
  ),
  makeApplication(
    'app-4',
    '44444444-4444-4444-4444-444444444444',
    'withdrawn',
  ),
]

function makeCandidateApplication(
  id: string,
  candidateId: string,
  status: ApplicationStatus,
  fullName: string,
  title: string,
): Application {
  return {
    ...makeApplication(id, candidateId, status),
    candidate: { id: candidateId, full_name: fullName, title },
  }
}

const searchableApplications: Application[] = [
  makeCandidateApplication(
    'app-a',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'applied',
    'Alice Nguyen',
    'Backend Engineer',
  ),
  makeCandidateApplication(
    'app-b',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'shortlisted',
    'Bao Tran',
    'Product Designer',
  ),
  makeCandidateApplication(
    'app-c',
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    'offered',
    'Carol Le',
    'Frontend Engineer',
  ),
]

function renderBoard(props: Partial<React.ComponentProps<typeof HiringPipelineBoard>> = {}) {
  return render(
    <MemoryRouter>
      <HiringPipelineBoard applications={applications} {...props} />
    </MemoryRouter>,
  )
}

function renderSearchableBoard() {
  return render(
    <MemoryRouter>
      <HiringPipelineBoard applications={searchableApplications} />
    </MemoryRouter>,
  )
}

function getSearchInput() {
  return screen.getByRole('searchbox', {
    name: 'Tìm ứng viên theo tên hoặc chức danh',
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('HiringPipelineBoard', () => {
  it('renders every pipeline column', () => {
    renderBoard()

    ;[
      'Ứng tuyển',
      'Đang xem xét',
      'Phỏng vấn',
      'Đề nghị',
      'Đã tuyển dụng',
      'Đã đóng',
    ].forEach((label) => {
      expect(screen.getByRole('region', { name: `Cột ${label}` })).toBeInTheDocument()
    })
  })

  it('maps legacy shortlisted applications into the screening column', () => {
    renderBoard()

    const screening = screen.getByRole('region', { name: 'Cột Đang xem xét' })
    expect(within(screening).getByText('Ứng viên 22222222')).toBeInTheDocument()
    expect(within(screening).getByText('Lọt vòng ngắn')).toBeInTheDocument()
  })

  it('groups applications under status-matched columns', () => {
    renderBoard()

    const offered = screen.getByRole('region', { name: 'Cột Đề nghị' })
    expect(within(offered).getByText('Ứng viên 33333333')).toBeInTheDocument()

    const terminal = screen.getByRole('region', { name: 'Cột Đã đóng' })
    expect(within(terminal).getByText('Ứng viên 44444444')).toBeInTheDocument()

    const applied = screen.getByRole('region', { name: 'Cột Ứng tuyển' })
    expect(within(applied).getByText('Ứng viên 11111111')).toBeInTheDocument()
  })

  it('disables the status update control for withdrawn applications', () => {
    renderBoard()

    expect(
      screen.getByRole('button', {
        name: /Cập nhật trạng thái cho đơn ứng tuyển app-4/i,
      }),
    ).toBeDisabled()
  })

  it('opens the application detail modal', async () => {
    mockedGetApplicationDetail.mockResolvedValue({
      id: 'app-1',
      candidate_id: '11111111-1111-1111-1111-111111111111',
      job_id: 'job-1',
      job_title: 'Backend Engineer',
      company_name: 'Acme Corp',
      status: 'applied',
      created_at: '2026-01-20T00:00:00Z',
      updated_at: '2026-01-20T00:00:00Z',
      candidate: null,
      resume: null,
      parsed_job: null,
      interviews: [],
    })

    renderBoard()

    fireEvent.click(
      screen.getByRole('button', { name: /Xem hồ sơ ứng viên 11111111/i }),
    )

    await waitFor(() => {
      expect(
        screen.getByRole('dialog', { name: 'Chi tiết đơn ứng tuyển' }),
      ).toBeInTheDocument()
    })
  })

  it('filters applications by candidate name (case-insensitive, trimmed)', () => {
    renderSearchableBoard()

    fireEvent.change(getSearchInput(), { target: { value: '  ALICE  ' } })

    expect(screen.getByText('Alice Nguyen')).toBeInTheDocument()
    expect(screen.queryByText('Bao Tran')).not.toBeInTheDocument()
    expect(screen.queryByText('Carol Le')).not.toBeInTheDocument()
  })

  it('filters applications by candidate title', () => {
    renderSearchableBoard()

    fireEvent.change(getSearchInput(), { target: { value: 'engineer' } })

    expect(screen.getByText('Alice Nguyen')).toBeInTheDocument()
    expect(screen.getByText('Carol Le')).toBeInTheDocument()
    expect(screen.queryByText('Bao Tran')).not.toBeInTheDocument()
  })

  it('recalculates column counts from the filtered set', () => {
    renderSearchableBoard()

    fireEvent.change(getSearchInput(), { target: { value: 'alice' } })

    const applied = screen.getByRole('region', { name: 'Cột Ứng tuyển' })
    const offered = screen.getByRole('region', { name: 'Cột Đề nghị' })
    expect(within(applied).getByText('1')).toBeInTheDocument()
    expect(within(offered).getByText('0')).toBeInTheDocument()
    expect(
      within(offered).getByText('Không có ứng viên'),
    ).toBeInTheDocument()
  })

  it('keeps the legacy shortlisted projection while filtering', () => {
    renderSearchableBoard()

    fireEvent.change(getSearchInput(), { target: { value: 'bao' } })

    const screening = screen.getByRole('region', { name: 'Cột Đang xem xét' })
    expect(within(screening).getByText('Bao Tran')).toBeInTheDocument()
    expect(within(screening).getByText('Lọt vòng ngắn')).toBeInTheDocument()
  })

  it('shows a search-empty state that is distinct from an empty pipeline and can be cleared', () => {
    renderSearchableBoard()

    fireEvent.change(getSearchInput(), { target: { value: 'nobody' } })

    const emptyState = screen.getByRole('status')
    expect(
      within(emptyState).getByText('Không tìm thấy ứng viên phù hợp'),
    ).toBeInTheDocument()

    fireEvent.click(
      within(emptyState).getByRole('button', { name: /Xóa tìm kiếm/i }),
    )

    expect(screen.getByText('Alice Nguyen')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByText('Không tìm thấy ứng viên phù hợp')).not.toBeInTheDocument()
  })

  it('offers no search control when there are no applications at all', () => {
    render(
      <MemoryRouter>
        <HiringPipelineBoard applications={[]} />
      </MemoryRouter>,
    )

    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
    expect(screen.queryByText('Không tìm thấy ứng viên phù hợp')).not.toBeInTheDocument()
  })
})
