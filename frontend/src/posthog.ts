import posthog from 'posthog-js'

const posthogKey = import.meta.env.VITE_POSTHOG_KEY
const posthogHost = import.meta.env.VITE_POSTHOG_HOST

export const isPostHogConfigured = Boolean(posthogKey && posthogHost)

if (posthogKey && posthogHost) {
  posthog.init(posthogKey, {
    api_host: posthogHost,
    defaults: '2026-08-30',
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
