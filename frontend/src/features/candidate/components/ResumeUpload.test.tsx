import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ResumeUpload } from './ResumeUpload'
import * as aiApi from '@/api/ai'
import type { ParsedResume } from '@/types/ai'

const mockParsedResume: ParsedResume = {
  full_name: 'John Doe',
  email: 'john@example.com',
  phone: '+84123456789',
  title: 'Software Engineer',
  summary: 'Experienced engineer.',
  total_years_experience: 5,
  skills: ['Python', 'FastAPI'],
  experiences: [],
  education: [],
  certifications: [],
  languages: [],
}

vi.mock('@/api/ai', () => ({
  parseResume: vi.fn(),
}))

const mockedParseResume = vi.mocked(aiApi.parseResume)

function makePdfFile(name = 'resume.pdf', size = 1024): File {
  const blob = new Blob(['%PDF-1.4 fake pdf'], { type: 'application/pdf' })
  const file = new File([blob], name, { type: 'application/pdf' })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ResumeUpload', () => {
  it('rejects non-PDF files', async () => {
    render(<ResumeUpload />)

    const input = screen.getByLabelText('Tải lên CV PDF') as HTMLElement
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

    const txtFile = new File(['hello'], 'resume.txt', { type: 'text/plain' })
    Object.defineProperty(txtFile, 'size', { value: 100 })
    fireEvent.change(fileInput, { target: { files: [txtFile] } })

    await waitFor(() => {
      expect(screen.getByText('Chỉ chấp nhận tệp PDF.')).toBeInTheDocument()
    })
    expect(mockedParseResume).not.toHaveBeenCalled()
    expect(input).toBeTruthy()
  })

  it('rejects files larger than 10MB', async () => {
    render(<ResumeUpload />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const bigFile = makePdfFile('big.pdf', 11 * 1024 * 1024)
    fireEvent.change(fileInput, { target: { files: [bigFile] } })

    await waitFor(() => {
      expect(
        screen.getByText('Tệp quá lớn. Kích thước tối đa là 10MB.'),
      ).toBeInTheDocument()
    })
    expect(mockedParseResume).not.toHaveBeenCalled()
  })

  it('calls parseResume and shows loading state', async () => {
    let resolveParse!: (value: ParsedResume) => void
    mockedParseResume.mockReturnValue(
      new Promise((resolve) => {
        resolveParse = resolve
      }),
    )

    render(<ResumeUpload />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const pdfFile = makePdfFile('resume.pdf')
    fireEvent.change(fileInput, { target: { files: [pdfFile] } })

    await waitFor(() => {
      expect(mockedParseResume).toHaveBeenCalled()
      expect(
        screen.getByText('Đang tải lên và phân tích CV của bạn...'),
      ).toBeInTheDocument()
    })

    resolveParse(mockParsedResume)
  })

  it('shows error when upload fails', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, { response: { status: 400, data: { detail: 'Invalid PDF' } } })
    mockedParseResume.mockRejectedValue(error)

    render(<ResumeUpload />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const pdfFile = makePdfFile('resume.pdf')
    fireEvent.change(fileInput, { target: { files: [pdfFile] } })

    await waitFor(() => {
      expect(screen.getByText('Invalid PDF')).toBeInTheDocument()
    })
  })

  it('maps "Candidate profile required" to a friendly Vietnamese message', async () => {
    const error = new Error('Bad Request')
    Object.assign(error, {
      response: { status: 400, data: { detail: 'Candidate profile required' } },
    })
    mockedParseResume.mockRejectedValue(error)

    render(<ResumeUpload />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const pdfFile = makePdfFile('resume.pdf')
    fireEvent.change(fileInput, { target: { files: [pdfFile] } })

    await waitFor(() => {
      expect(
        screen.getByText(
          'Hồ sơ ứng viên chưa được tạo. Vui lòng tạo hồ sơ trước khi tải CV.',
        ),
      ).toBeInTheDocument()
    })
  })

  it('calls onParsed with the parsed resume on success', async () => {
    mockedParseResume.mockResolvedValue(mockParsedResume)
    const onParsed = vi.fn()

    render(<ResumeUpload onParsed={onParsed} />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const pdfFile = makePdfFile('resume.pdf')
    fireEvent.change(fileInput, { target: { files: [pdfFile] } })

    await waitFor(() => {
      expect(onParsed).toHaveBeenCalledWith(mockParsedResume, 'resume.pdf')
    })
  })
})