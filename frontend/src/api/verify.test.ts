import { afterEach, describe, expect, it, vi } from "vitest";
import { apiError } from "../test/apiError";
import { api } from "./client";
import { describeApiError } from "./errors";
import {
  VERIFY_MESSAGES,
  describeVoiceCheckError,
  isVoiceCheckPaused,
  pausedMessage,
  submitAttempt,
  type VerifyResult,
} from "./verify";

afterEach(() => {
  vi.restoreAllMocks();
});

const RESULT: VerifyResult = {
  decision: "incomplete",
  reason: "The passage was read correctly, but this account has no voiceprint yet and the liveness check isn't built yet.",
  content: { passed: true, score: 1, matched: 6, total: 6 },
  identity: "not_enrolled",
  liveness: "not_checked",
  attempts_left: 3,
  fallback_required: false,
};

describe("submitAttempt", () => {
  it("sends the recording and its attempt as a form upload", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: RESULT });
    const audio = new Blob(["fake audio"], { type: "audio/webm;codecs=opus" });

    await expect(submitAttempt(audio, "attempt-1")).resolves.toEqual(RESULT);

    const [url, body, options] = post.mock.calls[0];
    expect(url).toBe("/api/verify");
    expect(options).toEqual({ timeout: 90_000 });
    const form = body as FormData;
    expect(form.get("attempt_id")).toBe("attempt-1");
    const sent = form.get("audio") as File;
    expect(sent.type).toBe("audio/webm;codecs=opus");
    expect(sent.size).toBe(audio.size);
  });
});

describe("VERIFY_MESSAGES", () => {
  it.each([400, 413, 415, 422])("gives a voice-check message for %i", (status) => {
    expect(describeApiError(apiError(status), VERIFY_MESSAGES)).toBe(VERIFY_MESSAGES[status]);
  });

  it("leaves rate limits and outages to the shared messages", () => {
    expect(describeApiError(apiError(429, {}, { "retry-after": "60" }), VERIFY_MESSAGES)).toBe(
      "Too many attempts. Please try again in 1 minute.",
    );
    expect(describeApiError(apiError(503), VERIFY_MESSAGES)).toBe(
      "VoiceGuard is temporarily unavailable. Please try again shortly.",
    );
  });
});

describe("voice-check pause", () => {
  it.each([
    ["900", "Voice checks are paused after too many failed attempts. Please try again in 15 minutes."],
    ["60", "Voice checks are paused after too many failed attempts. Please try again in 1 minute."],
    ["5", "Voice checks are paused after too many failed attempts. Please try again in 1 minute."],
  ])("turns Retry-After %s seconds into minutes", (seconds, message) => {
    expect(describeVoiceCheckError(apiError(423, {}, { "retry-after": seconds }))).toBe(message);
  });

  it.each([undefined, "0", "soon"])("falls back when Retry-After is %s", (seconds) => {
    const headers: Record<string, string> = seconds === undefined ? {} : { "retry-after": seconds };
    expect(describeVoiceCheckError(apiError(423, {}, headers))).toBe(pausedMessage(undefined));
    expect(pausedMessage(undefined)).toMatch(/try again later/);
  });

  it("never shows the server's own text", () => {
    const error = apiError(423, { detail: "locked: voice_failures doc 42" }, { "retry-after": "60" });

    expect(describeVoiceCheckError(error)).not.toMatch(/voice_failures/);
  });

  it("is told apart from other errors", () => {
    expect(isVoiceCheckPaused(apiError(423))).toBe(true);
    expect(isVoiceCheckPaused(apiError(429))).toBe(false);
    expect(isVoiceCheckPaused(new Error("boom"))).toBe(false);
  });

  it("leaves other statuses to the usual messages", () => {
    expect(describeVoiceCheckError(apiError(400))).toBe(VERIFY_MESSAGES[400]);
    expect(describeVoiceCheckError(apiError(503))).toBe(describeApiError(apiError(503)));
    expect(describeVoiceCheckError(apiError(400), {})).toBe(describeApiError(apiError(400)));
  });
});
