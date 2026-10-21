import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MockAdapter from 'axios-mock-adapter'

import apiClient, { API_BASE_URL } from './client'
import {
  getApplicationMatchExplanation,
  refreshApplicationMatchExplanation,
} from './applications'
import type { ApplicationMatchExplanationResponse } from '@/types/ai'

function makeExplanation(): ApplicationMatchExplanationResponse {
  return {
    application_id: 'app-1',
    overall_score: 82.5,
    score_breakdown: {
      overall_score: 82.5,
      cosine_similarity: 0.71,
      skill_coverage_score: 0.67,
      preferred_skill_coverage_score: 0.5,
      experience_match_score: 1,
      education_score: 0.5,
      project_score: 0.4,
    },
    summary: 'Kết quả đối sánh tự động.',
    summary_source: 'deterministic',
    skill_evaluations: [
      {
        skill_name: 'Python',
        requirement_type: 'required',
        status: 'matched_evidenced',
        explanation: 'Được liệt kê trong CV.',
        evidence: [
          {
            section: 'skills',
            field_name: 'skills',
            item_index: 0,
            item_title: null,
            quote: 'Python',
          },
        ],
      },
    ],
    experience_evaluations: [],
    key_strengths: ['Kỹ năng Python đáp ứng yêu cầu.'],
    areas_for_inquiry: ['Hỏi sâu hơn về kinh nghiệm Python.'],
    evidence: [],
    data_limitations: [],
    confidence: null,
    model_version: null,
    generated_at: '2026-01-01T00:00:00+00:00',
    cache_state: 'not_cached',
  }
}

function headerValue(
  headers: Record<string, unknown>,
  name: string,
): unknown {
  return headers[name] ?? headers[name.toLowerCase()]
}

describe('applications API match explanation client', () => {
  let mockAdapter: MockAdapter

  beforeEach(() => {
    mockAdapter = new MockAdapter(apiClient)
  })

  afterEach(() => {
    mockAdapter.restore()
    vi.restoreAllMocks()
  })

  it('GET requests the canonical match-explanation route', async () => {
    const payload = makeExplanation()
    mockAdapter
      .onGet(
        `${API_BASE_URL}/applications/app-1/match-explanation`,
      )
      .reply(200, payload)

    const result = await getApplicationMatchExplanation('app-1')

    expect(mockAdapter.history.get).toHaveLength(1)
    expect(mockAdapter.history.get[0].url).toBe(
      '/applications/app-1/match-explanation',
    )
    expect(mockAdapter.history.get[0].method).toBe('get')
    expect(mockAdapter.history.post).toHaveLength(0)
    expect(result).toEqual(payload)
    expect(result.cache_state).toBe('not_cached')
  })

  it('GET unwraps the response envelope rather than returning response data', async () => {
    const payload = makeExplanation()
    mockAdapter
      .onGet(
        `${API_BASE_URL}/applications/app-1/match-explanation`,
      )
      .reply(200, payload)

    const result = await getApplicationMatchExplanation('app-1')

    expect(result).toEqual(payload)
    expect(result).not.toHaveProperty('data')
    expect(result).not.toHaveProperty('status')
  })

  it('POST requests the canonical refresh route', async () => {
    const payload = makeExplanation()
    mockAdapter
      .onPost(
        `${API_BASE_URL}/applications/app-1/match-explanation/refresh`,
      )
      .reply(200, payload)

    const result = await refreshApplicationMatchExplanation(
      'app-1',
      'caller-key-1',
    )

    expect(mockAdapter.history.post).toHaveLength(1)
    expect(mockAdapter.history.post[0].url).toBe(
      '/applications/app-1/match-explanation/refresh',
    )
    expect(mockAdapter.history.post[0].method).toBe('post')
    expect(result).toEqual(payload)
  })

  it('POST sends the caller-supplied Idempotency-Key header', async () => {
    mockAdapter
      .onPost(
        `${API_BASE_URL}/applications/app-1/match-explanation/refresh`,
      )
      .reply(200, makeExplanation())

    await refreshApplicationMatchExplanation('app-1', 'caller-key-1')

    const request = mockAdapter.history.post[0]
    expect(
      headerValue(request.headers as Record<string, unknown>, 'Idempotency-Key'),
    ).toBe('caller-key-1')
  })

  it('POST generates a UUID Idempotency-Key when none is supplied', async () => {
    const generated = '123e4567-e89b-42d3-a456-426614174000'
    vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(
      generated as `${string}-${string}-${string}-${string}-${string}`,
    )
    mockAdapter
      .onPost(
        `${API_BASE_URL}/applications/app-1/match-explanation/refresh`,
      )
      .reply(200, makeExplanation())

    await refreshApplicationMatchExplanation('app-1')

    const request = mockAdapter.history.post[0]
    const key = headerValue(
      request.headers as Record<string, unknown>,
      'Idempotency-Key',
    )
    expect(key).toBe(generated)
    expect(typeof key).toBe('string')
    expect((key as string).length).toBeGreaterThan(0)
  })

  it('POST propagates HTTP errors through the shared error contract', async () => {
    mockAdapter
      .onPost(
        `${API_BASE_URL}/applications/app-1/match-explanation/refresh`,
      )
      .reply(429, { detail: 'AI quota exhausted' })

    await expect(
      refreshApplicationMatchExplanation('app-1', 'caller-key-1'),
    ).rejects.toMatchObject({
      response: {
        status: 429,
        data: { detail: 'AI quota exhausted' },
      },
    })
  })

  it('GET propagates HTTP errors through the shared error contract', async () => {
    mockAdapter
      .onGet(
        `${API_BASE_URL}/applications/app-1/match-explanation`,
      )
      .reply(404, { detail: 'Application not found' })

    await expect(
      getApplicationMatchExplanation('app-1'),
    ).rejects.toMatchObject({
      response: {
        status: 404,
        data: { detail: 'Application not found' },
      },
    })
  })

  it('POST does not automatically retry a failed refresh', async () => {
    mockAdapter
      .onPost(
        `${API_BASE_URL}/applications/app-1/match-explanation/refresh`,
      )
      .replyOnce(503, { detail: 'AI Match unavailable' })

    await expect(
      refreshApplicationMatchExplanation('app-1', 'caller-key-1'),
    ).rejects.toMatchObject({ response: { status: 503 } })

    expect(mockAdapter.history.post).toHaveLength(1)
  })
})
