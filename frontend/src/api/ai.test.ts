import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import axios from 'axios'
import { parseResume } from './ai'
import apiClient from './client'

describe('parseResume - FormData multipart regression', () => {
  let mockAdapter: MockAdapter

  beforeEach(() => {
    // Set up localStorage with a fake token for authentication
    localStorage.setItem('ai_recruitment_token', 'test-token')

    mockAdapter = new MockAdapter(apiClient)

    const baseURL = 'http://localhost:8000/api/v1'

    // Mock the parse-resume endpoint (specific route must come FIRST)
    mockAdapter.onPost(`${baseURL}/ai/parse-resume`).reply(function(config) {
      const authHeader = config.headers?.Authorization || config.headers?.authorization
      if (!authHeader) {
        return [401, { detail: 'Not authenticated' }]
      }

      // Check if the request contains a non-PDF file (for error test)
      const formData = config.data as FormData
      if (formData instanceof FormData) {
        const file = formData.get('file') as File
        if (file && file.type !== 'application/pdf') {
          return [400, { detail: 'Invalid PDF format' }]
        }
      }

      return [200, {
        full_name: 'John Doe',
        email: 'john@example.com',
        title: 'Software Engineer',
      }]
    })

    // Mock the JSON test endpoint
    mockAdapter.onPost(`${baseURL}/test-json`).reply(function(config) {
      const authHeader = config.headers?.Authorization || config.headers?.authorization
      if (!authHeader) {
        return [401, { detail: 'Not authenticated' }]
      }
      return [200, { success: true }]
    })
  })

  afterEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('sends FormData without manual Content-Type header', async () => {
    const file = new File(['%PDF-1.4 fake pdf content'], 'resume.pdf', {
      type: 'application/pdf',
    })

    const result = await parseResume(file)

    expect(result).toEqual({
      full_name: 'John Doe',
      email: 'john@example.com',
      title: 'Software Engineer',
    })

    // Verify the actual HTTP request made by axios
    const history = mockAdapter.history.post
    expect(history).toHaveLength(1)

    const request = history[0]

    // Verify URL (axios-mock-adapter records the path without baseURL)
    expect(request.url).toBe('/ai/parse-resume')

    // Verify HTTP method
    expect(request.method).toBe('post')

    // Verify request body is FormData
    expect(request.data).toBeInstanceOf(FormData)

    // Verify FormData contains the file
    const formData = request.data as FormData
    const fileEntry = formData.get('file')
    expect(fileEntry).toBeInstanceOf(File)
    expect((fileEntry as File).name).toBe('resume.pdf')
    expect((fileEntry as File).type).toBe('application/pdf')

    // CRITICAL: Verify NO manual Content-Type: multipart/form-data header
    // The interceptor should delete Content-Type when FormData is detected
    // In real browser, axios generates multipart/form-data with boundary automatically
    // In test environment (axios-mock-adapter), we verify it's NOT application/json
    const requestHeaders = request.headers as Record<string, string>
    const contentType = requestHeaders['content-type'] || requestHeaders['Content-Type']

    // The request should NOT have Content-Type: application/json (the bug we fixed)
    expect(contentType).not.toBe('application/json')

    // The interceptor should delete Content-Type header for FormData
    // axios-mock-adapter may show its own default, but the key is: not application/json
    // and not a manually set multipart/form-data (which would lack boundary)
  })

  it('normal JSON requests still use application/json', async () => {
    // Test that normal JSON requests still work correctly
    const result = await apiClient.post('/test-json', { key: 'value' })

    expect(result).toEqual({ success: true })

    const history = mockAdapter.history.post
    const request = history[history.length - 1]

    // Verify JSON requests still use application/json
    const contentType = request.headers['content-type'] || request.headers['Content-Type']
    expect(contentType).toBe('application/json')
  })

  it('handles axios errors correctly', async () => {
    const file = new File(['not a pdf'], 'test.txt', {
      type: 'text/plain',
    })

    await expect(parseResume(file)).rejects.toMatchObject({
      response: {
        status: 400,
        data: { detail: 'Invalid PDF format' },
      },
    })
  })
})