import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Phase 2A4 — host-app integration:
  //   * /api/biometric/service/* → DP4500 (the host-app backend with the
  //     Ed25519 service endpoints). Hardcoded to 8000 because the
  //     ServiceAPIKey was minted against that backend's DB; do not move
  //     without rotating the key.
  //   * everything else (/api/*, /media/*) → clinic backend on 8001.
  //
  // Vite matches the most specific proxy entry first, so the service
  // entry must come BEFORE the generic /api entry.
  const clinicBackendTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001'
  const dp4500Target = env.VITE_DP4500_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api/biometric/service': {
          target: dp4500Target,
          changeOrigin: true,
        },
        '/api': {
          target: clinicBackendTarget,
          changeOrigin: true,
        },
        '/media': {
          target: clinicBackendTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
