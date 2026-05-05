export type FingerprintCapture = {
  provider: 'MOCK'
  template: string
  quality: number
  deviceSerial: string
  capturedAt: string
}

export type FingerprintDeviceStatus = {
  connected: boolean
  provider: 'MOCK'
  deviceSerial: string
  message: string
}

const MOCK_DEVICE_SERIAL = 'MOCK-SECU-GEN-HP20-001'

function wait(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function normalizeSeed(seed: string) {
  return seed
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
}

export async function checkMockFingerprintDevice(): Promise<FingerprintDeviceStatus> {
  await wait(350)
  return {
    connected: true,
    provider: 'MOCK',
    deviceSerial: MOCK_DEVICE_SERIAL,
    message: 'Simulador SecuGen listo',
  }
}

export async function enrollMockFingerprint(seed: string): Promise<FingerprintCapture> {
  await wait(900)
  const normalizedSeed = normalizeSeed(seed) || 'cliente'
  return {
    provider: 'MOCK',
    template: `mock-secugen-template:${normalizedSeed}`,
    quality: 91,
    deviceSerial: MOCK_DEVICE_SERIAL,
    capturedAt: new Date().toISOString(),
  }
}

export async function verifyMockFingerprint(template: string): Promise<FingerprintCapture> {
  await wait(700)
  return {
    provider: 'MOCK',
    template,
    quality: 94,
    deviceSerial: MOCK_DEVICE_SERIAL,
    capturedAt: new Date().toISOString(),
  }
}
