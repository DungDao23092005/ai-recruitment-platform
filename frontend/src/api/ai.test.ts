import { describe, expect, it, vi, beforeEach } from 'vitest'
import axios from 'axios'

import { parseResume } from './ai'

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  const mockInstance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  }
  return {
    __esModule: true,
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => mockInstance),
    },
  }
})

const mockAxiosInstance = axios.create as ReturnType<typeof vi.fn>
const instance = mockAxiosInstance.mock.results[0].value

beforeEach(() => {
  vi.clearAllMocks()
})

describe('parseResume', () => {
  it('sends multipart/form-data request without manual Content-Type header', async () => {
    const mockParsedResume = {
      full_name: 'John Doe',
      email: 'john@example.com',
      title: 'Software Engineer',
    }
    instance.post.mockResolvedValue({ data: mockParsedResume })

    const file = new File(['%PDF-1.4 fake pdf content'], 'resume.pdf', {
      type: 'application/pdf',
    })

    await parseResume(file)

    expect(instance.post).toHaveBeenCalled()
    const callArgs = instance.post.mock.calls[0]

    // Verify URL
    expect(callArgs[0]).toBe('/ai/parse-resume')

    // Verify request body is FormData
    expect(callArgs[1]).toBeInstanceOf(FormData)

    // Verify FormData contains the file
    const formData = callArgs[1] as FormData
    const fileEntry = formData.get('file')
    expect(fileEntry).toBeInstanceOf(File)
    expect((fileEntry as File).name).toBe('resume.pdf')
    expect((fileEntry as File).type).toBe('application/pdf')

    // CRITICAL: Verify NO manual Content-Type: multipart/form-data header
    // The config object is the third argument (callArgs[2])
    const config = callArgs[2]
    if (config) {
      // The config.headers may be an AxiosHeaders object or plain object
      const headers = config.headers
      if (headers && typeof headers === 'object') {
        // Check if Content-Type was manually set to multipart/form-data
        const contentType = headers['Content-Type'] || headers['content-type']
        expect(contentType).not.toBe('multipart/form-data')
      }
    }
  })

  it('does not include Content-Type: multipart/form-data when passing config without it', async () => {
    const mockParsedResume = {
      full_name: 'Jane Doe',
      title: 'Backend Engineer',
    }
    instance.post.mockResolvedValue({ data: mockParsedResume })

    const file = new File(['%PDF-1.4'], 'cv.pdf', {
      type: 'application/pdf',
    })

    // Call with a config that doesn't have Content-Type
    const config = { timeout: 30000 }
    await parseResume(file, config)

    expect(instance.post).toHaveBeenCalled()
    const callArgs = instance.post.mock.calls[0]
    const configArg = callArgs[2]

    if (configArg) {
      const headers = configArg.headers
      if (headers && typeof headers === 'object') {
        const contentType = headers['Content-Type'] || headers['content-type']
        expect(contentType).not.toBe('multipart/form-data')
      }
    }
  })

  it('handles axios errors correctly', async () => {
    const errorResponse = {
      response: {
        status: 400,
        data: { detail: 'Invalid PDF format' },
      },
    }
    instance.post.mockRejectedValue({
      response: errorResponse,
    })

    const file = new File(['not a pdf'], 'test.txt', {
      type: 'text/plain',
    })

    await expect(parseResume(file)).rejects.toMatchObject({
      response: {
        response: {
          status: 400,
          data: { detail: 'Invalid PDF format' },
        },
      },
    })
  })
})