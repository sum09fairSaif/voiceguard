import { describe, expect, it } from "vitest";
import { apiError, networkError } from "../test/apiError";
import { MESSAGES, describeApiError, invalidFields } from "./errors";

describe("describeApiError", () => {
  it("explains a missing connection", () => {
    expect(describeApiError(networkError())).toBe(MESSAGES.network);
  });

  it.each([
    [401, MESSAGES.signedOut],
    [422, MESSAGES.invalid],
    [503, MESSAGES.unavailable],
    [500, MESSAGES.unknown],
  ])("gives our own message for %i", (status, message) => {
    expect(describeApiError(apiError(status))).toBe(message);
  });

  it("never shows the server's own text", () => {
    const error = apiError(500, { detail: "Traceback: database password=hunter2" });

    expect(describeApiError(error)).toBe(MESSAGES.unknown);
  });

  it("lets a screen override a status it understands", () => {
    const message = describeApiError(apiError(409), { 409: "Email already used." });

    expect(message).toBe("Email already used.");
  });

  it.each([
    ["120", "Too many attempts. Please try again in 2 minutes."],
    ["60", "Too many attempts. Please try again in 1 minute."],
    ["5", "Too many attempts. Please try again in 1 minute."],
  ])("turns Retry-After %s seconds into minutes", (seconds, message) => {
    expect(describeApiError(apiError(429, {}, { "retry-after": seconds }))).toBe(message);
  });

  it("handles a rate limit with no Retry-After", () => {
    expect(describeApiError(apiError(429))).toBe(
      "Too many attempts. Please wait a while and try again.",
    );
  });

  it("handles something that isn't an API error at all", () => {
    expect(describeApiError(new Error("boom"))).toBe(MESSAGES.unknown);
  });
});

describe("invalidFields", () => {
  it("lists the fields the server rejected", () => {
    const error = apiError(422, {
      detail: [
        { type: "value_error", loc: ["body", "email"], msg: "not an email" },
        { type: "missing", loc: ["body", "full_name"], msg: "Field required" },
      ],
    });

    expect(invalidFields(error)).toEqual(["email", "full_name"]);
  });

  it("is empty for other errors", () => {
    expect(invalidFields(apiError(409))).toEqual([]);
    expect(invalidFields(networkError())).toEqual([]);
  });
});
