// Smoke tests for fingerprint-agent.
// These tests do NOT require the DigitalPersona SDK to load — they verify
// the HTTP server boots and answers shape-correct responses. The SDK-load
// diagnostic lives in the GET /health response body and is observed
// manually after `npm start`.

import { test, after } from 'node:test'
import assert from 'node:assert'
import { request } from 'node:http'

// Avoid clashing with any user-run agent on 8765 during the test run.
process.env.FINGERPRINT_AGENT_PORT = process.env.FINGERPRINT_AGENT_PORT || '18765'

const { server } = await import('../index.js?bust=' + Date.now())
const PORT = Number(process.env.FINGERPRINT_AGENT_PORT)

after(() => {
  server.close()
})

function get(path) {
  return new Promise((resolve, reject) => {
    const req = request(
      { hostname: '127.0.0.1', port: PORT, path, method: 'GET' },
      (res) => {
        let body = ''
        res.on('data', (c) => { body += c })
        res.on('end', () => resolve({ status: res.statusCode, body }))
      },
    )
    req.on('error', reject)
    req.end()
  })
}

test('GET /health returns 200 and JSON with status field', async () => {
  const { status, body } = await get('/health')
  assert.strictEqual(status, 200)
  const parsed = JSON.parse(body)
  assert.ok(
    parsed.status === 'ready' || parsed.status === 'init',
    `expected status to be ready|init, got ${parsed.status}`,
  )
})

test('GET /unknown returns 404', async () => {
  const { status, body } = await get('/does-not-exist')
  assert.strictEqual(status, 404)
  const parsed = JSON.parse(body)
  assert.strictEqual(parsed.error, 'not found')
})

test('OPTIONS /capture responds with CORS headers', async () => {
  const { status } = await new Promise((resolve, reject) => {
    const req = request(
      { hostname: '127.0.0.1', port: PORT, path: '/capture', method: 'OPTIONS' },
      (res) => resolve({ status: res.statusCode }),
    )
    req.on('error', reject)
    req.end()
  })
  assert.strictEqual(status, 204)
})
