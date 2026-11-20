// First, before analytics or anything else can read the address: takes a
// password-reset link's token out of it (#109).
import './resetLinkToken.ts'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/inter/600.css'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/sn-pro/400.css'
import '@fontsource/sn-pro/600.css'
import '@fontsource/sn-pro/700.css'
import './index.css'
import './posthog.ts'
import { restorePostHogIdentity } from './api/session.ts'
import App from './App.tsx'

restorePostHogIdentity()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
