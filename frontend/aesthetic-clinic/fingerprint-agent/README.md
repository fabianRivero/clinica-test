# fingerprint-agent

Local HTTP bridge from the clinic browser to the DigitalPersona 4500 reader
via the **Lite Client** (`DpHost`) WebChannel host.

This is a Phase 4 spike (Plan B) for environments where the in-browser
`WebChannel` path does not work in dev — typically because the Lite Client
holds an exclusive handle on the reader and the browser cannot open a parallel
channel. The agent runs as a small Node.js process on the operator's
workstation and exposes a tiny HTTP API the browser can call instead.

## Prerequisites

- DigitalPersona **Lite Client 4.x** installed and running (`DpHost` service
  is up; check `services.msc`).
- The DP4500 reader plugged in and visible to `DpHost` (verify in the Lite
  Client UI: device should show in the device list).
- Node.js >= 18 (tested on Node 24).
- The clinic frontend's `node_modules/@digitalpersona/*` packages are
  available — the agent resolves them from the sibling
  `../node_modules/@digitalpersona/` directory by default. You can also run
  `npm install` in this directory to create a local copy.

## Start

```sh
# from this directory
npm start
# or
node index.js
# or with a custom port
FINGERPRINT_AGENT_PORT=9000 node index.js
```

The server listens on `http://127.0.0.1:8765` by default (loopback only — not
reachable from the network).

## Endpoints

### `GET /health`

Returns the agent's boot status. Used to confirm the SDK loaded.

```json
{ "status": "ready", "error": null, "sdk": { "hasFingerprintWebApi": true, ... } }
```

If the SDK fails to load, you'll get `{ "status": "init", "error": "<reason>" }`
and the agent will not be able to perform captures until the issue is fixed.

### `POST /capture`

Triggers a fingerprint capture. **Not implemented in the spike** — returns
`501 { "error": "capture not yet implemented" }`. The next iteration will
instantiate `Fingerprint.WebApi`, call `startAcquisition(SampleFormat.PngImage)`,
collect the `SamplesAcquired` event, and return the base64 sample in the
response body.

## CORS

All responses include permissive CORS headers
(`Access-Control-Allow-Origin: *`) so the Vite dev server at `:5173` can call
the agent without proxy configuration.

## Spike scope and limits

This iteration only proves whether the `@digitalpersona/*` SDK bundles can
be evaluated inside a Node.js process. The bundles are **browser-only IIFEs**
(no ESM exports, no `node` condition in `exports`) that reach for `window`,
`navigator`, `crypto.getRandomValues`, `sessionStorage`, `btoa`/`atob`,
etc. We shim the minimum globals needed to evaluate them.

**Spike result**: the SDK DOES load in Node.js once the browser globals are
shimmed. `Fingerprint.WebApi` instantiates cleanly and exposes
`enumerateDevices`, `getDeviceInfo`, `startAcquisition`, `stopAcquisition`.
`GET /health` reports `{"status":"ready","sdk":{"hasFingerprintWebApi":true}}`
after a successful capture attempt.

**Still required for real capture**: a working `XMLHttpRequest` shim. The
websdk bundle defines and uses XHR inside `WebChannelClient`, but only when
`connect()`/`sendDataTxt()` is called — so the bundle loads fine without it,
but a capture attempt will fail until we provide one. Candidate polyfills:
[`xhr2`](https://www.npmjs.com/package/xhr2) (low-level) or
[`jsdom`](https://www.npmjs.com/package/jsdom) (heavier, but already gives
us a full DOM). The next iteration picks one based on whether we need DOM
bits beyond XHR.
