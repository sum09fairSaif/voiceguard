import { afterEach, describe, expect, it, vi } from "vitest";
import { apiError } from "../test/apiError";
import { api } from "./client";
import { describeApiError } from "./errors";
import { VERIFY_MESSAGES, submitAttempt, type VerifyResult } from "./verify";

afterEach(() => {
  vi.restoreAllMocks();
});

const RESULT: VerifyResult = {
  decision: "incomplete",
  reason: "The passage was read correctly, but this account has no voiceprint yet and the liveness check isn't built yet.",
  content: { passed: true, score: 1, matched: 6, total: 6 },
  identity: "not_enrolled",
  liveness: "not_checked",
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
