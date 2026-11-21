import posthog, { type CaptureResult } from 'posthog-js'

const posthogKey = import.meta.env.VITE_POSTHOG_KEY
const posthogHost = import.meta.env.VITE_POSTHOG_HOST

export const isPostHogConfigured = Boolean(posthogKey && posthogHost)

// Addresses PostHog records on its own. Everything after "#" is dropped from
// them: a password-reset link carries its token there (#109). The token is
// already taken out of the address before PostHog starts (resetLinkToken.ts);
// this is the backstop.
const URL_PROPERTIES = ['$current_url', '$initial_current_url', '$referrer', '$initial_referrer']

function withoutFragment(value: unknown): unknown {
  return typeof value === 'string' ? value.split('#', 1)[0] : value
}

export function stripUrlFragments(event: CaptureResult | null): CaptureResult | null {
  if (!event) return event
  for (const bag of [event.properties, event.$set, event.$set_once]) {
    if (!bag) continue
    for (const key of URL_PROPERTIES) {
      if (key in bag) bag[key] = withoutFragment(bag[key])
    }
  }
  return event
}

if (posthogKey && posthogHost) {
  posthog.init(posthogKey, {
    api_host: posthogHost,
    defaults: '2026-08-30',
    before_send: stripUrlFragments,
    // Match the app's session, which lives in one tab and ends when it closes,
    // so an identity never outlives sign-out or leaks into another tab.
    persistence: 'sessionStorage',
    // Recordings would capture the enrollment and verification screens.
    disable_session_recording: true,
    capture_exceptions: {
      capture_unhandled_errors: true,
      capture_unhandled_rejections: true,
      capture_console_errors: false,
    },
    logs: {
      serviceName: 'voiceguard-frontend',
      environment: import.meta.env.MODE,
    },
  })
} else if (import.meta.env.DEV) {
  for (const variableName of ['VITE_POSTHOG_KEY', 'VITE_POSTHOG_HOST']) {
    if (!import.meta.env[variableName]) {
      console.error(
        new Error(
          `${variableName} variable required by PostHog is missing or un-configured, this causes events to be silently missed. This error stops appearing once ${variableName} is configured`,
        ),
      )
    }
  }
}

export default posthog
