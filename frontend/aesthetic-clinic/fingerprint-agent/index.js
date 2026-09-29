// fingerprint-agent — local HTTP bridge from clinic browser to DigitalPersona 4500
// via the Lite Client (DpHost) WebChannel on the operator workstation.
//
// SPIKE: this iteration only proves that the SDK bundles (websdk.client.ui.js and
// fingerprint.sdk.js) can be evaluated in a Node.js process at all. The real
// capture flow is the next iteration once we know the SDK even loads.
//
// Why this is non-trivial: the @digitalpersona/* packages are browser-only
// IIFE/UMD bundles. They reach for `window.*`, `XMLHttpRequest`, `navigator`,
// `crypto.getRandomValues`, etc. There is NO Node entry point and NO ESM export
// in their package.json `exports` map. We shim the bare minimum globals needed
// to *parse and load* the SDK files in Node, then report whether they did.

import { createServer } from 'node:http'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import vm from 'node:vm'

const PORT = Number(process.env.FINGERPRINT_AGENT_PORT || 8765)

const __dirname = dirname(fileURLToPath(import.meta.url))

// --- SDK paths ------------------------------------------------------------
// We resolve the SDK from the clinic frontend's node_modules to keep one
// canonical copy. Falls back to ./node_modules if the user has installed it
// locally (preferred for production).
const FRONTEND_SDK = join(
  __dirname,
  '..',
  'node_modules',
  '@digitalpersona',
)
const LOCAL_SDK = join(__dirname, 'node_modules', '@digitalpersona')

function resolveSdkPath(pkg, file) {
  const candidates = [
    join(FRONTEND_SDK, pkg, 'dist', file),
    join(LOCAL_SDK, pkg, 'dist', file),
  ]
  for (const p of candidates) {
    try {
      readFileSync(p)
      return p
    } catch {}
  }
  return null
}

// --- SDK load -------------------------------------------------------------
//
// The SDK bundles are NOT loadable via `import`. Their package.json `exports`
// only has a `browser` condition, and the bundles themselves are IIFEs that
// register `window.WebSdk` / `window.Fingerprint`. In Node.js we have to:
//   1. Build a sandbox with a `window` global that points at the sandbox
//      itself, so `var Foo = (function(){...})()` in the browser becomes
//      `sandbox.Foo` in Node.
//   2. Read the bundle source and `runInContext` it.
//   3. After both bundles load, the agent exposes the SDK globals back to
//      the rest of the process via `globalThis`.

let sdkReady = false
let initError = null
let sdkInfo = null

async function ensureSdk() {
  if (sdkReady) return
  if (initError) throw initError

  try {
    const websdkPath = resolveSdkPath('websdk', 'websdk.client.ui.js')
    const fpPath = resolveSdkPath('fingerprint', 'fingerprint.sdk.js')
    if (!websdkPath) throw new Error('Could not locate @digitalpersona/websdk dist file')
    if (!fpPath) throw new Error('Could not locate @digitalpersona/fingerprint dist file')

    // Build a fresh sandbox. We map `window` to itself so the IIFE pattern
    // `(function(WebSdk){...})(window.WebSdk = window.WebSdk || {})` and the
    // implicit `var X` hoisting onto `window` both work. We also expose
    // `globalThis` so bundles that reach for `self` or globals find something.
    //
    // The @digitalpersona SDKs are browser-only IIFE bundles that reach
    // for a handful of browser globals at module-evaluation time. The
    // shims below are the bare minimum to *parse and load* the bundles.
    // The capture flow itself (which talks to DpHost via WebChannelClient)
    // will additionally need a working XMLHttpRequest — that is the next
    // iteration. If you see `ReferenceError: X is not defined` from
    // `ensureSdk`, add the missing global here.
    const noopStorage = {
      _store: new Map(),
      getItem(k) { return this._store.has(k) ? this._store.get(k) : null },
      setItem(k, v) { this._store.set(k, String(v)) },
      removeItem(k) { this._store.delete(k) },
      clear() { this._store.clear() },
      key(i) { return Array.from(this._store.keys())[i] ?? null },
      get length() { return this._store.size },
    }
    const sandbox = {
      console,
      setTimeout,
      clearTimeout,
      setInterval,
      clearInterval,
      Buffer,
      process,
      // Node 16+ has global atob/btoa as globals. Make sure the sandbox sees them.
      atob,
      btoa,
      // Minimal `navigator` shim. The websdk bundle reads `navigator.appName`
      // at module-evaluation time for legacy browser sniffing. The values
      // here are placeholders — none of the SDK capture flow uses them at
      // load time. If a real capture needs UA bits, this is the seam.
      navigator: { appName: 'Netscape', userAgent: 'node-fingerprint-agent/0.1' },
      // sessionStorage / localStorage: the SDK stores the WebSdk session id
      // and config here. In-memory shim is fine for the spike.
      sessionStorage: { ...noopStorage },
      localStorage: { ...noopStorage },
      // addEventListener is only used by the legacy load-time/keyboard
      // collector inside the SJCL entropy pool — we never call it.
      addEventListener() {},
      removeEventListener() {},
    }
    sandbox.window = sandbox
    sandbox.self = sandbox
    sandbox.globalThis = sandbox

    // Node 19+ has globalThis.crypto. The SDK uses it for SRP entropy.
    if (typeof sandbox.crypto === 'undefined' && globalThis.crypto) {
      sandbox.crypto = globalThis.crypto
    }

    // XMLHttpRequest polyfill (Phase 4 PR C). The websdk bundle's
    // WebChannelClient reaches for `XMLHttpRequest` from inside
    // `connect()` / `sendDataTxt()` (NOT at module-evaluation time,
    // so the bundle loads without it). We inject the `xhr2` shim
    // into the sandbox BEFORE running the bundles so the prototype
    // chain is consistent — both the IIFE and the post-IIFE
    // WebChannelClient see the same constructor.
    //
    // `xhr2` is CommonJS; the dynamic import returns
    // `{ default: <XMLHttpRequestCtor> }` under ESM (`"type": "module"`).
    const xhr2Module = await import('xhr2')
    const Xhr2 = xhr2Module.default || xhr2Module
    sandbox.XMLHttpRequest = Xhr2

    vm.createContext(sandbox)

    const websdkSrc = readFileSync(websdkPath, 'utf8')
    vm.runInContext(websdkSrc, sandbox, { filename: 'websdk.client.ui.js' })

    const fpSrc = readFileSync(fpPath, 'utf8')
    vm.runInContext(fpSrc, sandbox, { filename: 'fingerprint.sdk.js' })

    // Promote the SDK globals from sandbox to this process so the capture
    // route can use them.
    globalThis.WebSdk = sandbox.WebSdk
    globalThis.Fingerprint = sandbox.Fingerprint

    sdkInfo = {
      websdkPath,
      fpPath,
      hasWebSdk: typeof sandbox.WebSdk === 'object',
      hasFingerprint: typeof sandbox.Fingerprint === 'object',
      hasFingerprintWebApi: Boolean(sandbox.Fingerprint?.WebApi),
    }
    sdkReady = true
  } catch (e) {
    initError = e
    throw e
  }
}

// --- Capture flow ---------------------------------------------------------
//
// Phase 4 PR C: real capture wired against `Fingerprint.WebApi`. The
// SDK's high-level facade (`WebApi`) wraps the underlying
// `WebSdk.WebChannelClient` and exposes:
//     onSamplesAcquired(event)   — event.samples is the base64 PNG
//                                 payload, event.deviceUid is the
//                                 SDK-reported reader identifier.
//     onQualityReported(event)   — event.quality is a `QualityCode`
//                                 enum; Good (0) means accept.
//     onErrorOccurred(event)     — event.error is a numeric SDK code.
//     onAcquisitionStarted(event)— fired when WebChannel connected
//                                 and the reader began sampling.
//     onAcquisitionStopped(event)— fired after stopAcquisition().
//
// The handshake Phase 3.1 wired in the browser also applies here:
// we wait for BOTH `onSamplesAcquired` and `onQualityReported`
// before resolving. The Promise resolves on the first Good-quality
// verdict that pairs with a stashed sample; any non-Good quality
// triggers a quality-too-low rejection so the wizard surfaces a
// retryable UX message instead of a hardware fault.

const SAMPLE_FORMAT_PNG_IMAGE = 5 // Fingerprint.SampleFormat.PngImage
const CAPTURE_TIMEOUT_MS = 30_000

/**
 * Run a single fingerprint capture against the SDK's `WebApi`
 * facade. The function is exported so unit tests can wire a mock
 * `globalThis.Fingerprint` and verify the event-handler wiring
 * without booting the real SDK or DpHost.
 *
 * Resolves with `{ templateB64, qualityScore, deviceSerial, width,
 * height }` on a Good-quality sample. Rejects with an Error whose
 * `.code` property is one of:
 *   - `'sdk_not_initialized'`  — `globalThis.Fingerprint.WebApi` is missing
 *   - `'no_reader'`            — `enumerateDevices()` returned []
 *   - `'quality_too_low'`      — SDK reported a non-Good quality code
 *   - `'sdk_error'`            — SDK fired onErrorOccurred
 *   - `'capture_timeout'`      — no sample + no quality within 30s
 */
export async function captureFingerprint() {
  if (!globalThis.Fingerprint || !globalThis.Fingerprint.WebApi) {
    const err = new Error('SDK not initialized')
    err.code = 'sdk_not_initialized'
    throw err
  }

  // `debug: false` keeps the SDK from spamming the console with
  // WebChannel frames during normal operator captures.
  const webApi = new globalThis.Fingerprint.WebApi({ debug: false })

  return new Promise((resolve, reject) => {
    let settled = false
    let stashedSample = null
    let stashedDeviceUid = null

    const settleReject = (err) => {
      if (settled) return
      settled = true
      cleanup()
      // Best-effort stop; swallows errors because the Promise is
      // already settling to a rejection.
      webApi.stopAcquisition().catch(() => undefined)
      reject(err)
    }

    const settleResolve = (payload) => {
      if (settled) return
      settled = true
      cleanup()
      resolve(payload)
    }

    const cleanup = () => {
      clearTimeout(timeoutHandle)
      webApi.onSamplesAcquired = undefined
      webApi.onQualityReported = undefined
      webApi.onErrorOccurred = undefined
      webApi.onAcquisitionStarted = undefined
      webApi.onAcquisitionStopped = undefined
    }

    // 30s hard timeout. Mirrors the browser wrapper's behavior —
    // if the SDK never delivers a sample + quality within 30s, the
    // operator is staring at a hung modal. Reject so the wizard
    // can fall through to NO_AGENT.
    const timeoutHandle = setTimeout(() => {
      const err = new Error('capture timeout after 30s')
      err.code = 'capture_timeout'
      settleReject(err)
    }, CAPTURE_TIMEOUT_MS)

    webApi.onErrorOccurred = (event) => {
      const err = new Error(`SDK error code ${event.error}`)
      err.code = 'sdk_error'
      err.sdkErrorCode = event.error
      settleReject(err)
    }

    webApi.onSamplesAcquired = (event) => {
      // The SDK may deliver samples for multiple fingers when the
      // operator touches + removes + touches again. We stash the
      // first sample and let the quality verdict decide; if a
      // second sample arrives we overwrite (the operator is
      // re-trying — the more recent frame is the better one).
      stashedSample = event.samples
      stashedDeviceUid = event.deviceUid

      // If the quality verdict arrived first (rare, but the SDK
      // does not guarantee event order), close the handshake now.
      if (stashedQuality !== null && stashedQuality.deviceUid === event.deviceUid) {
        if (stashedQuality.code === 0 /* Good */) {
          settleResolve({
            templateB64: stashedSample,
            qualityScore: 0,
            deviceSerial: stashedDeviceUid,
            width: 0,
            height: 0,
          })
        } else {
          const err = new Error(`quality too low: ${stashedQuality.code}`)
          err.code = 'quality_too_low'
          err.qualityCode = stashedQuality.code
          settleReject(err)
        }
      }
    }

    let stashedQuality = null

    webApi.onQualityReported = (event) => {
      // Quality arrived before the sample — stash and wait.
      if (stashedSample === null) {
        stashedQuality = { deviceUid: event.deviceUid, code: event.quality }
        return
      }

      // Quality arrived for a DIFFERENT device than the stashed
      // sample — defensive guard. Reject so the anomaly surfaces
      // instead of silently corrupting the capture result.
      if (stashedDeviceUid !== event.deviceUid) {
        const err = new Error('quality report does not match the active reader')
        err.code = 'sdk_error'
        settleReject(err)
        return
      }

      if (event.quality === 0 /* Good */) {
        settleResolve({
          templateB64: stashedSample,
          qualityScore: 0,
          deviceSerial: stashedDeviceUid,
          width: 0,
          height: 0,
        })
        return
      }

      const err = new Error(`quality too low: ${event.quality}`)
      err.code = 'quality_too_low'
      err.qualityCode = event.quality
      settleReject(err)
    }

    webApi.onAcquisitionStarted = () => {
      // No-op for now — the SDK signals readiness but the actual
      // capture result is delivered via onSamplesAcquired +
      // onQualityReported. Reserved for future "show spinner" UX.
    }

    webApi.onAcquisitionStopped = () => {
      // No-op for now — fires after stopAcquisition() completes.
      // Reserved for future cleanup hooks.
    }

    // enumerateDevices() returns an array of device UIDs (strings).
    // An empty array means DpHost has no reader enumerated — return
    // a typed error so the HTTP layer maps it to 503.
    webApi
      .enumerateDevices()
      .then((devices) => {
        if (!devices || devices.length === 0) {
          const err = new Error('no reader enumerated by DpHost')
          err.code = 'no_reader'
          settleReject(err)
          return
        }
        // startAcquisition's promise resolves on the FIRST
        // onAcquisitionStarted event. We don't await it here —
        // the catch only needs to handle SDK init failures; the
        // per-sample lifecycle is event-driven via the handlers
        // above.
        return webApi.startAcquisition(SAMPLE_FORMAT_PNG_IMAGE)
      })
      .catch((err) => {
        if (err && err.code) {
          // Already a typed error from the handlers above — just
          // forward so the Promise settles once.
          settleReject(err)
          return
        }
        const wrapped = new Error(err && err.message ? err.message : String(err))
        wrapped.code = 'sdk_error'
        settleReject(wrapped)
      })
  })
}

// --- HTTP server ----------------------------------------------------------

function jsonResponse(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(body))
}

const server = createServer(async (req, res) => {
  // CORS for the Vite dev server at :5173
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
  res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
  if (req.method === 'OPTIONS') {
    res.writeHead(204)
    res.end()
    return
  }

  if (req.method === 'GET' && req.url === '/health') {
    return jsonResponse(res, 200, {
      status: sdkReady ? 'ready' : 'init',
      error: initError ? String(initError.message || initError) : null,
      sdk: sdkInfo,
    })
  }

  if (req.method === 'POST' && req.url === '/capture') {
    let body = ''
    req.on('data', (chunk) => { body += chunk })
    req.on('end', async () => {
      try {
        await ensureSdk()
        if (!sdkReady) {
          return jsonResponse(res, 503, {
            error: 'SDK not initialized',
            detail: String(initError?.message || initError),
          })
        }
        const capture = await captureFingerprint()
        return jsonResponse(res, 200, {
          templateB64: capture.templateB64,
          qualityScore: capture.qualityScore,
          deviceSerial: capture.deviceSerial,
          width: capture.width,
          height: capture.height,
        })
      } catch (e) {
        const code = e && e.code ? e.code : 'sdk_error'
        // Map typed capture errors to HTTP statuses the frontend
        // already understands (503 = no reader; everything else
        // is an SDK fault that the wizard treats as a hardware
        // failure).
        if (code === 'no_reader') {
          return jsonResponse(res, 503, {
            error: 'no reader enumerated',
            detail: e.message,
          })
        }
        return jsonResponse(res, 500, {
          error: code,
          detail: e && e.message ? e.message : String(e),
        })
      }
    })
    return
  }

  jsonResponse(res, 404, { error: 'not found' })
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[fingerprint-agent] listening on http://127.0.0.1:${PORT}`)
})

// Graceful shutdown so `node --test` can spin the server up and down.
function shutdown() {
  server.close(() => process.exit(0))
}
process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)

// Export for tests. Production code (`node index.js`) never imports this.
export { server, ensureSdk }
