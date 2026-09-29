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

    // NOTE on XMLHttpRequest: the websdk bundle DEFINES and USES XHR inside
    // its WebChannelClient, but at *module-evaluation* time it is only
    // referenced from inside function bodies — not from the top level.
    // So the bundle loads without XHR. The shim is only needed at
    // connect() / sendDataTxt() time. That is the next iteration's problem.
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
        // TODO(next iteration): instantiate Fingerprint.WebApi, wire up
        // onSamplesAcquired, call startAcquisition(SampleFormat.PngImage),
        // and stream the base64 sample back. The hard part is whether the
        // WebChannelClient inside the SDK can actually reach DpHost from
        // Node — that requires a working XHR transport.
        return jsonResponse(res, 501, { error: 'capture not yet implemented' })
      } catch (e) {
        return jsonResponse(res, 500, { error: String(e.message || e) })
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
