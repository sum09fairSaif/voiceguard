import posthog from 'posthog-js'

const posthogKey = import.meta.env.VITE_POSTHOG_KEY
const posthogHost = import.meta.env.VITE_POSTHOG_HOST
export const isPosthogConfigured = Boolean(posthogKey && posthogHost)

if (!isPosthogConfigured) {
  if (import.meta.env.DEV) {
    console.error(
      new Error(
        `${!posthogKey ? 'VITE_POSTHOG_KEY' : 'VITE_POSTHOG_HOST'} variable required by PostHog is missing or un-configured, this causes events to be silently missed. This error stops appearing once ${!posthogKey ? 'VITE_POSTHOG_KEY' : 'VITE_POSTHOG_HOST'} is configured`,
      ),
    )
  }
} else {
  posthog.init(posthogKey, {
    api_host: posthogHost,
    capture_exceptions: {
      capture_console_errors: false,
      capture_unhandled_errors: true,
      capture_unhandled_rejections: true,
    },
    defaults: '2026-08-30',
    logs: {
      serviceName: 'voiceguard-frontend',
      environment: import.meta.env.MODE,
    },
  })
}

export default posthog
