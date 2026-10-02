/** `useSignedUrl` hook + `<SignedImage>`/`<SignedLink>` (slice 3b). */

import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'

import { API_BASE_URL } from './api/apiClient'

// Absolute URLs arrive as `http(s)://host[:port]/media/<key>` from
// `request.build_absolute_uri(file.url)`; relative URLs arrive as `/media/<key>`.
// Strip either prefix so the signed-url endpoint receives the bare bucket key.
const ABSOLUTE_MEDIA_RE = /^https?:\/\/[^/]+\/media\//

const SIGNED_URL_PATH = '/api/media/signed-url/'
const TTL_FLOOR_SECONDS = 300
const TTL_SAFETY_SECONDS = 60
const BACKOFF_503_MS = 30_000

export interface SignedUrl {
  url: string
  expires_at: string
  ttl_seconds: number
}

interface CacheEntry { url: string; expiresAtMs: number }

const cache: Map<string, CacheEntry> = new Map()
const backoffUntil: Map<string, number> = new Map()

export interface UseSignedUrlResult { url: string | null; loading: boolean; error: string | null }

export async function fetchSignedUrl(path: string): Promise<SignedUrl> {
  const cached = cache.get(path)
  if (cached && cached.expiresAtMs > Date.now()) {
    return {
      url: cached.url,
      expires_at: new Date(cached.expiresAtMs).toISOString(),
      ttl_seconds: Math.max(1, Math.round((cached.expiresAtMs - Date.now()) / 1000)),
    }
  }
  if ((backoffUntil.get(path) ?? 0) > Date.now()) {
    throw new Error('signed-url backoff active')
  }
  const response = await fetch(
    `${API_BASE_URL}${SIGNED_URL_PATH}?path=${encodeURIComponent(path)}`,
    { credentials: 'include', headers: { Accept: 'application/json' } },
  )
  if (response.status === 503) {
    backoffUntil.set(path, Date.now() + BACKOFF_503_MS)
    throw new Error(`signed-url endpoint unavailable (${response.status})`)
  }
  if (!response.ok) {
    throw new Error(`signed-url request failed (${response.status})`)
  }
  const body = (await response.json()) as SignedUrl
  const ttl = Math.max(1, body.ttl_seconds - TTL_SAFETY_SECONDS)
  cache.set(path, {
    url: body.url,
    expiresAtMs: Date.now() + Math.min(ttl, TTL_FLOOR_SECONDS) * 1000,
  })
  return body
}

export function useSignedUrl(path: string | null): UseSignedUrlResult {
  const [url, setUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(path !== null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    if (!path) {
      setUrl(null); setLoading(false); setError(null)
      return
    }
    const cached = cache.get(path)
    if (cached && cached.expiresAtMs > Date.now()) {
      setUrl(cached.url); setLoading(false); setError(null)
      return
    }
    setLoading(true); setError(null)
    fetchSignedUrl(path)
      .then((signed) => {
        if (cancelled) return
        setUrl(signed.url); setLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
    return () => { cancelled = true }
  }, [path])
  return { url, loading, error }
}

export function __resetSignedUrlCacheForTests(): void {
  cache.clear(); backoffUntil.clear()
}

function normalizePath(raw: string | null | undefined): string | null {
  if (!raw) return null
  if (ABSOLUTE_MEDIA_RE.test(raw)) return raw.replace(ABSOLUTE_MEDIA_RE, '')
  return raw.startsWith('/media/') ? raw.slice('/media/'.length) : raw
}

interface SignedImageProps {
  src: string | null | undefined; alt: string; className?: string; style?: CSSProperties
}

export function SignedImage({ src, alt, className, style }: SignedImageProps) {
  const { url, loading, error } = useSignedUrl(normalizePath(src))
  if (loading || !url) {
    return (
      <span
        className={className}
        style={style}
        aria-busy={loading ? true : undefined}
        role={error ? 'img' : undefined}
        aria-label={error ? `${alt} (no disponible)` : alt}
      />
    )
  }
  return <img src={url} alt={alt} className={className} style={style} />
}

interface SignedLinkProps {
  href: string | null | undefined; download?: boolean; target?: string
  rel?: string; className?: string; children: ReactNode
}

export function SignedLink({ href, download, target, rel, className, children }: SignedLinkProps) {
  const { url, loading } = useSignedUrl(normalizePath(href))
  if (!url) {
    return <span className={className} aria-busy={loading ? true : undefined}>{children}</span>
  }
  return (
    <a
      href={url}
      {...(download ? { download: true } : {})}
      {...(target ? { target } : {})}
      {...(rel ? { rel } : {})}
      className={className}
    >
      {children}
    </a>
  )
}
