import { afterEach, describe, expect, it, vi } from "vitest";
import { apiError, networkError } from "../test/apiError";
import { api } from "./client";
import { ENROLL_MESSAGES, addSample, describeEnrollError, getEnrollment, isAlreadyEnrolled, startOver } from "./enroll";
import { MESSAGES } from "./errors";

const status = { status: "in_progress", samples_accepted: 1, samples_required: 3, prompt: "amber lantern river" };

afterEach(() => {
  vi.restoreAllMocks();
});

describe("enrollment calls", () => {
  it("reads the enrollment status", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: status });
    await expect(getEnrollment()).resolves.toEqual(status);
    expect(get).toHaveBeenCalledWith("/api/enroll");
  });

  it("sends one sample as the audio form field, with a long timeout", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: status });
    const audio = new Blob(["x"], { type: "audio/webm" });

    await expect(addSample(audio)).resolves.toEqual(status);
    const [path, form, options] = post.mock.calls[0];
    expect(path).toBe("/api/enroll/samples");
    expect((form as FormData).get("audio")).toBeInstanceOf(Blob);
    expect(options).toEqual({ timeout: 90_000 });
  });

  it("starts over by deleting the unfinished samples", async () => {
    const del = vi.spyOn(api, "delete").mockResolvedValue({ data: { ...status, status: "not_started", samples_accepted: 0 } });
    await expect(startOver()).resolves.toMatchObject({ samples_accepted: 0 });
    expect(del).toHaveBeenCalledWith("/api/enroll/samples");
  });
});

describe("describeEnrollError", () => {
  // The backend's current wording (backend/routers/enroll.py). If it changes,
  // these fail and the key phrases need updating.
  it.each([
    ["That recording was too short or too quiet. Please read the whole sentence clearly, close to your microphone.", ENROLL_MESSAGES.tooShort],
    ["That recording was too loud and sounds distorted. Please move a little further from your microphone and try again.", ENROLL_MESSAGES.tooLoud],
    ["That recording doesn't sound like your earlier ones. Please record it again in the same quiet place. If this keeps happening, start over.", ENROLL_MESSAGES.inconsistent],
    ["We couldn't read that recording. Please record it again.", ENROLL_MESSAGES.unreadable],
  ])("rewords a rejected sample in our own words: %s", (detail, message) => {
    expect(describeEnrollError(apiError(422, { detail }))).toBe(message);
  });

  it("never shows the server's sentence itself", () => {
    const detail = "That recording was too short or too quiet. Please read the whole sentence clearly, close to your microphone.";
    expect(describeEnrollError(apiError(422, { detail }))).not.toBe(detail);
  });

  it("falls back to a general retry message for an unknown rejection", () => {
    expect(describeEnrollError(apiError(422, { detail: "Something new" }))).toBe(ENROLL_MESSAGES.rejected);
    expect(describeEnrollError(apiError(422, { detail: [{ loc: ["body", "audio"] }] }))).toBe(ENROLL_MESSAGES.rejected);
  });

  it("explains a recording that's too long or in the wrong format", () => {
    expect(describeEnrollError(apiError(413))).toBe(ENROLL_MESSAGES.tooLong);
    expect(describeEnrollError(apiError(415))).toBe(ENROLL_MESSAGES.format);
  });

  it("uses the usual messages for limits, outages and no connection", () => {
    expect(describeEnrollError(apiError(503))).toBe(MESSAGES.unavailable);
    expect(describeEnrollError(apiError(429, {}, { "retry-after": "120" }))).toContain("2 minutes");
    expect(describeEnrollError(networkError())).toBe(MESSAGES.network);
  });

  it("recognises an account that's already enrolled", () => {
    expect(isAlreadyEnrolled(apiError(409))).toBe(true);
    expect(isAlreadyEnrolled(apiError(422))).toBe(false);
  });
});
