import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    // Use jsdom for the window/document globals the wrapper touches
    // when it lazy-injects the SDK IIFE.
    environment: 'jsdom',
    // The capture wrapper has a 30s hard timeout; we lower it via
    // test globals if needed (see the test file for the mock-timeout
    // approach).
    globals: false,
    include: ['src/**/__tests__/**/*.test.ts'],
  },
})