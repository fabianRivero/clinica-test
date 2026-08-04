/// <reference types="vite/client" />

/**
 * Custom Vite environment variables for the SPA.
 *
 * `VITE_BIOMETRIC_SUSPENDED` is baked at build time. When set, the
 * biometric client short-circuits capture/match/enroll calls so no
 * HTTP request is emitted and the agent heartbeat poll is skipped.
 * The backend `BIOMETRIC_SUSPENDED` env var remains authoritative;
 * if the values diverge, the backend 503 response wins.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_API_PROXY_TARGET?: string
  readonly VITE_BIOMETRIC_SUSPENDED?: 'true' | 'false' | '1' | '0' | '' | undefined
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}