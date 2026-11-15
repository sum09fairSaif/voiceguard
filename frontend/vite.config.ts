/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The security headers live in vercel.json (what the live site sends). `vite
// preview` sends the same ones, so a policy problem shows up locally first.
// Locally the API may run on localhost:8000, which the live policy doesn't list.
type VercelHeaders = { headers: { source: string; headers: { key: string; value: string }[] }[] }
const vercel = JSON.parse(readFileSync(new URL('./vercel.json', import.meta.url), 'utf8')) as VercelHeaders
const previewHeaders = Object.fromEntries(
  vercel.headers[0].headers.map(({ key, value }) => [
    key,
    key === 'Content-Security-Policy'
      ? value.replace('connect-src ', 'connect-src http://localhost:8000 ').replace('; upgrade-insecure-requests', '')
      : value,
  ]),
)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  preview: { headers: previewHeaders },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
