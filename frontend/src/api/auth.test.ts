import { afterEach, describe, expect, it, vi } from "vitest";
import { apiError, networkError } from "../test/apiError";
import { WRONG_CREDENTIALS, describeLoginError, lockedOutMessage, logIn, signup } from "./auth";
import { api } from "./client";
import { MESSAGES } from "./errors";

const account = {
  user: { id: "u1", full_name: "Sam Lee", email: "sam@example.com", created_at: "2026-10-22T12:00:00Z" },
  access_token: "token-1",
  token_type: "bearer",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("signup", () => {
  it("creates the account and returns it with a token", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: account });
    const body = { full_name: "Sam Lee", email: "sam@example.com", password: "Correct-horse-9" };

    await expect(signup(body)).resolves.toEqual(account);
    expect(post).toHaveBeenCalledWith("/api/auth/signup", body);
  });
});

describe("logIn", () => {
  it("sends the email and password and returns the account with a token", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: account });
    const body = { email: "sam@example.com", password: "Correct-horse-9" };

    await expect(logIn(body)).resolves.toEqual(account);
    expect(post).toHaveBeenCalledWith("/api/auth/login", body);
  });
});

describe("describeLoginError", () => {
  it("says the credentials are wrong without saying which one", () => {
    expect(describeLoginError(apiError(401))).toBe(WRONG_CREDENTIALS);
  });

  it("explains a lockout with the minutes left from Retry-After", () => {
    const error = apiError(423, { detail: "server text" }, { "retry-after": "1740" });
    expect(describeLoginError(error)).toBe(lockedOutMessage(1740));
    expect(describeLoginError(error)).toContain("29 minutes");
  });

  it("never shows the server's own text for a lockout", () => {
    const error = apiError(423, { detail: "Internal lock id 42" }, { "retry-after": "60" });
    expect(describeLoginError(error)).not.toContain("Internal");
  });

  it("falls back to the usual messages for other problems", () => {
    expect(describeLoginError(apiError(422))).toBe(MESSAGES.invalid);
    expect(describeLoginError(apiError(503))).toBe(MESSAGES.unavailable);
    expect(describeLoginError(networkError())).toBe(MESSAGES.network);
  });
});

describe("lockedOutMessage", () => {
  it("rounds up to whole minutes and says 1 minute in the singular", () => {
    expect(lockedOutMessage(30)).toContain("in 1 minute.");
    expect(lockedOutMessage(61)).toContain("in 2 minutes.");
  });

  it("still makes sense without a usable Retry-After", () => {
    expect(lockedOutMessage(undefined)).toContain("try again later");
    expect(lockedOutMessage(Number("abc"))).toContain("try again later");
  });
});
