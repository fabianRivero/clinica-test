/** Tests for `useSignedUrl` hook + cache layer (slice 3). */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { __resetSignedUrlCacheForTests, fetchSignedUrl } from '../media'

const SIGNED_PAYLOAD = {
  url: 'https://bucket.example/x.pdf?sig=abc',
  expires_at: '2026-10-01T15:15:00Z',
  ttl_seconds: 900,
}

function fakeFetch(body: unknown = SIGNED_PAYLOAD): typeof fetch {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  ) as unknown as typeof fetch
}

describe('fetchSignedUrl', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    __resetSignedUrlCacheForTests()
  })
  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('hits the endpoint with the path query param and returns the url', async () => {
    const fetchMock = fakeFetch() as unknown as ReturnType<typeof vi.fn>
    global.fetch = fetchMock
    const result = await fetchSignedUrl('fichas/x.pdf')
    expect(result.url).toBe('https://bucket.example/x.pdf?sig=abc')
    expect(result.ttl_seconds).toBe(900)
    const called = String((fetchMock.mock.calls[0] as unknown as [unknown])[0])
    expect(called).toContain('/api/media/signed-url/')
    expect(called).toContain('path=fichas%2Fx.pdf')
  })

  it('caches the url until the cache window expires', async () => {
    let calls = 0
    const fetchMock = vi.fn(async () => {
      calls += 1
      return new Response(JSON.stringify(SIGNED_PAYLOAD), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }) as unknown as ReturnType<typeof vi.fn>
    global.fetch = fetchMock
    const first = await fetchSignedUrl('fichas/y.pdf')
    const second = await fetchSignedUrl('fichas/y.pdf')
    expect(calls).toBe(1)
    expect(second.url).toBe(first.url)
  })

  it('clears the cache when __resetSignedUrlCacheForTests runs', async () => {
    let calls = 0
    const fetchMock = vi.fn(async () => {
      calls += 1
      return new Response(JSON.stringify(SIGNED_PAYLOAD), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }) as unknown as ReturnType<typeof vi.fn>
    global.fetch = fetchMock
    await fetchSignedUrl('shared/z.pdf')
    await fetchSignedUrl('shared/z.pdf')
    expect(calls).toBe(1)
    __resetSignedUrlCacheForTests()
    await fetchSignedUrl('shared/z.pdf')
    expect(calls).toBe(2)
  })
})
