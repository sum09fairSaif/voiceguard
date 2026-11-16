import posthog from 'posthog-js'

const apiKey = import.meta.env.VITE_POSTHOG_KEY
const apiHost = import.meta.env.VITE_POSTHOG_HOST

export const isPostHogConfigured = Boolean(apiKey && apiHost)

if (apiKey && apiHost) {
  posthog.init(apiKey, {
    api_host: apiHost,
    capture_pageview: 'history_change',
    capture_exceptions: {
      capture_unhandled_errors: true,
      capture_unhandled_rejections: true,
      capture_console_errors: false,
    },
    defaults: '2026-08-30',
    logs: {
      serviceName: 'voiceguard-frontend',
      environment: import.meta.env.MODE,
    },
  })
} else if (import.meta.env.DEV) {
  if (!apiKey) {
    console.error(
      new Error(
        'VITE_POSTHOG_KEY variable required by PostHog is missing or un-configured, this causes events to be silently missed. This error stops appearing once VITE_POSTHOG_KEY is configured',
      ),
    )
  }

  if (!apiHost) {
    console.error(
      new Error(
        'VITE_POSTHOG_HOST variable required by PostHog is missing or un-configured, this causes events to be silently missed. This error stops appearing once VITE_POSTHOG_HOST is configured',
      ),
    )
  }
}

export default posthog
