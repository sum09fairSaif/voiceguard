import type { CaptureResult } from "posthog-js";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("posthog-js", () => ({ default: { init: vi.fn(), capture: vi.fn() } }));
vi.mock("posthog-js/dist/exception-autocapture.js", () => ({}));

// The test setup has already loaded ./posthog with the real posthog-js (via
// api/session), so load it again with the stand-in above.
vi.resetModules();
const { default: posthog } = await import("posthog-js");
const { ANALYTICS_OPTIONS, EVENT_FIELDS, isPostHogConfigured, onlyListedEvents, startAnalytics, track, trackingRefused } =
  await import("./posthog");

const SET_UP = { VITE_POSTHOG_KEY: "phc_test", VITE_POSTHOG_HOST: "https://us.i.posthog.com" };

function browser(signals: { doNotTrack?: string | null; globalPrivacyControl?: boolean } = {}): Navigator {
  return { doNotTrack: null, ...signals } as unknown as Navigator;
}

function event(name: string, properties: Record<string, unknown> = {}): CaptureResult {
  return { uuid: "1", event: name, properties: { $current_url: "https://app.example/", ...properties } } as CaptureResult;
}

beforeEach(() => {
  vi.mocked(posthog.init).mockClear();
  vi.mocked(posthog.capture).mockClear();
});

describe("starting analytics (#170)", () => {
  it("loads nothing without a key", () => {
    expect(startAnalytics({}, browser())).toBe(false);
    expect(startAnalytics({ VITE_POSTHOG_KEY: "phc_test" }, browser())).toBe(false);
    expect(posthog.init).not.toHaveBeenCalled();
  });

  it("starts with the key and host", () => {
    expect(startAnalytics(SET_UP, browser())).toBe(true);
    expect(posthog.init).toHaveBeenCalledWith("phc_test", expect.objectContaining({ api_host: SET_UP.VITE_POSTHOG_HOST }));
  });

  it.each([
    ["Do Not Track", { doNotTrack: "1" }],
    ["Global Privacy Control", { globalPrivacyControl: true }],
  ])("loads nothing when the browser sends %s", (_, signals) => {
    expect(trackingRefused(browser(signals))).toBe(true);
    expect(startAnalytics(SET_UP, browser(signals))).toBe(false);
    expect(posthog.init).not.toHaveBeenCalled();
  });

  it("still starts when Do Not Track is explicitly off", () => {
    expect(trackingRefused(browser({ doNotTrack: "0", globalPrivacyControl: false }))).toBe(false);
  });

  it("sends nothing while it's off, as in these tests", () => {
    expect(isPostHogConfigured).toBe(false);
    track("signed_in");
    expect(posthog.capture).not.toHaveBeenCalled();
  });
});

describe("what PostHog may do", () => {
  it("captures no clicks, heatmaps, dead clicks, recordings or page performance", () => {
    expect(ANALYTICS_OPTIONS).toMatchObject({
      autocapture: false,
      rageclick: false,
      capture_dead_clicks: false,
      capture_heatmaps: false,
      capture_performance: false,
      disable_session_recording: true,
    });
  });

  it("loads nothing from PostHog: no remote config, surveys, tours, chat, experiments or scripts", () => {
    expect(ANALYTICS_OPTIONS).toMatchObject({
      advanced_disable_flags: true,
      disable_surveys: true,
      disable_product_tours: true,
      disable_conversations: true,
      disable_web_experiments: true,
      disable_external_dependency_loading: true,
    });
  });

  it("still captures front-end errors, but not console errors", () => {
    expect(ANALYTICS_OPTIONS.capture_exceptions).toEqual({
      capture_unhandled_errors: true,
      capture_unhandled_rejections: true,
      capture_console_errors: false,
    });
  });
});

describe("only the listed events and fields leave the browser", () => {
  it.each(["$autocapture", "$rageclick", "$dead_click", "$web_vitals", "$snapshot", "survey shown", "made_up"])(
    "drops %s",
    (name) => {
      expect(onlyListedEvents(event(name))).toBeNull();
    },
  );

  it.each(["$pageview", "$pageleave", "$exception", "$identify"])("keeps PostHog's own %s", (name) => {
    expect(onlyListedEvents(event(name))?.event).toBe(name);
  });

  it("keeps an event's own fields and drops any other", () => {
    const sent = onlyListedEvents(
      event("voice_verification_completed", {
        decision: "rejected",
        identity: null,
        liveness: null,
        content_passed: null,
        score: 0.42,
        email: "sam@example.com",
        passage: "a fresh six word phrase here",
      }),
    );

    expect(sent?.properties).toEqual({
      $current_url: "https://app.example/",
      decision: "rejected",
      identity: null,
      liveness: null,
      content_passed: null,
    });
  });

  it("never lists a field that could carry personal data or a secret", () => {
    const fields = Object.values(EVENT_FIELDS).flat();
    for (const banned of ["email", "name", "full_name", "token", "password", "passage", "audio", "score"]) {
      expect(fields).not.toContain(banned);
    }
  });

  it("runs after the address check, so both apply", () => {
    expect(ANALYTICS_OPTIONS.before_send).toHaveLength(2);
    expect(ANALYTICS_OPTIONS.before_send).toContain(onlyListedEvents);
  });
});
