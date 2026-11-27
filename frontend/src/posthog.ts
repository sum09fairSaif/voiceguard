import posthog, { type CaptureResult, type PostHogConfig } from 'posthog-js'
// Bundled with the app, so front-end errors are still captured with PostHog's
// remote scripts switched off (#170).
import 'posthog-js/dist/exception-autocapture.js'

// The only events the app sends, each with the only fields it may carry
// (#170). Never form values, emails, names, tokens, passages, audio or scores.
export const EVENT_FIELDS = {
  account_created: [],
  signed_in: [],
  voice_id_enrollment_started: [],
  voice_id_sample_saved: ['samples_accepted', 'samples_required'],
  voice_id_enrollment_restarted: [],
  voice_id_enrollment_completed: [],
  voice_verification_submitted: [],
  // The per-check outcomes are null unless the server is set to show them (#112).
  voice_verification_completed: ['decision', 'identity', 'liveness', 'content_passed'],
} as const satisfies Record<string, readonly string[]>

export type AnalyticsEvent = keyof typeof EVENT_FIELDS
type Fields<E extends AnalyticsEvent> = Partial<
  Record<(typeof EVENT_FIELDS)[E][number], string | number | boolean | null>
>

// What PostHog sends on its own that we keep: page views, errors, and the
// link between a visit and the person once they sign in.
const POSTHOG_EVENTS = new Set(['$pageview', '$pageleave', '$exception', '$identify'])

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

// The last check before anything leaves the browser: an event that isn't on
// the list is dropped, and our own events lose any field that isn't theirs.
// PostHog's own "$" fields (browser, screen size, page address) stay.
export function onlyListedEvents(event: CaptureResult | null): CaptureResult | null {
  if (!event) return event
  if (POSTHOG_EVENTS.has(event.event)) return event
  if (!Object.hasOwn(EVENT_FIELDS, event.event)) return null
  const allowed: readonly string[] = EVENT_FIELDS[event.event as AnalyticsEvent]
  for (const key of Object.keys(event.properties ?? {})) {
    if (!key.startsWith('$') && !allowed.includes(key)) delete event.properties[key]
  }
  return event
}

// Do Not Track or Global Privacy Control: no analytics at all, not even
// loading PostHog (#170).
export function trackingRefused(browser: Navigator | undefined = globalThis.navigator): boolean {
  if (!browser) return false
  const legacy = browser as Navigator & { msDoNotTrack?: string; globalPrivacyControl?: boolean }
  const windowDnt = (globalThis as { doNotTrack?: string }).doNotTrack
  return (
    legacy.globalPrivacyControl === true ||
    [browser.doNotTrack, legacy.msDoNotTrack, windowDnt].some((value) => value === '1' || value === 'yes')
  )
}

export const ANALYTICS_OPTIONS: Partial<PostHogConfig> = {
  defaults: '2026-08-30',
  before_send: [stripUrlFragments, onlyListedEvents],
  // Match the app's session, which lives in one tab and ends when it closes,
  // so an identity never outlives sign-out or leaks into another tab.
  persistence: 'sessionStorage',
  // Only the named events: no clicks (with the clicked text), heatmaps,
  // rage or dead clicks, or page performance.
  autocapture: false,
  rageclick: false,
  capture_dead_clicks: false,
  capture_heatmaps: false,
  capture_performance: false,
  // Recordings would capture the enrollment and verification screens.
  disable_session_recording: true,
  // Nothing set from PostHog's side: no remote config or feature flags, no
  // surveys, tours, chat or experiments, and no scripts loaded from PostHog.
  // That's what lets the CSP leave PostHog's script host out (#170).
  advanced_disable_flags: true,
  disable_surveys: true,
  disable_product_tours: true,
  disable_conversations: true,
  disable_web_experiments: true,
  disable_external_dependency_loading: true,
  // Our own check comes first (trackingRefused); this is the backstop.
  respect_dnt: true,
  capture_exceptions: {
    capture_unhandled_errors: true,
    capture_unhandled_rejections: true,
    capture_console_errors: false,
  },
}

type AnalyticsEnv = { VITE_POSTHOG_KEY?: string; VITE_POSTHOG_HOST?: string; DEV?: boolean }

// Starts PostHog if it's set up and the browser hasn't asked not to be
// tracked. Returns whether it started.
export function startAnalytics(env: AnalyticsEnv, browser?: Navigator): boolean {
  const key = env.VITE_POSTHOG_KEY
  const host = env.VITE_POSTHOG_HOST
  if (!key || !host) {
    if (env.DEV) {
      for (const [name, value] of [['VITE_POSTHOG_KEY', key], ['VITE_POSTHOG_HOST', host]]) {
        if (!value) console.error(new Error(`${name} is not set, so analytics is off.`))
      }
    }
    return false
  }
  if (trackingRefused(browser)) return false
  posthog.init(key, { ...ANALYTICS_OPTIONS, api_host: host })
  return true
}

export const isPostHogConfigured = startAnalytics(import.meta.env)

// Sends one of the listed events. Does nothing while analytics is off.
export function track<E extends AnalyticsEvent>(event: E, fields?: Fields<E>): void {
  if (isPostHogConfigured) posthog.capture(event, fields)
}

export default posthog
