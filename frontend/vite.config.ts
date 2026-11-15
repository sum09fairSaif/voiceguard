/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// The security headers live in vercel.json (what the live site sends). `vite
// preview` sends the same ones, so a policy problem shows up locally first.
// Locally the API is wherever the build points (VITE_API_BASE_URL, often
// localhost:8000), which the live policy doesn't list, and there's no HTTPS.
type VercelHeaders = { headers: { source: string; headers: { key: string; value: string }[] }[] }
const vercel = JSON.parse(readFileSync(new URL('./vercel.json', import.meta.url), 'utf8')) as VercelHeaders

function previewHeaders(apiBaseUrl: string | undefined): Record<string, string> {
  let apiOrigin = 'http://localhost:8000'
  try {
    if (apiBaseUrl) apiOrigin = new URL(apiBaseUrl).origin
  } catch {
    // Not a URL: keep the local default.
  }
  return Object.fromEntries(
    vercel.headers[0].headers.map(({ key, value }) => [
      key,
      key === 'Content-Security-Policy'
        ? value.replace('connect-src ', `connect-src ${apiOrigin} `).replace('; upgrade-insecure-requests', '')
        : value,
    ]),
  )
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // process.env first, as Vite itself does, then the .env files.
  preview: { headers: previewHeaders(process.env.VITE_API_BASE_URL ?? loadEnv(mode, process.cwd()).VITE_API_BASE_URL) },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
}))
