import { afterEach, describe, expect, it, vi } from "vitest";
import { TEST_USER } from "../test/session";
import { api } from "./client";
import { endSession, isSignedIn, restorePostHogIdentity, startSession } from "./session";

afterEach(() => {
  vi.restoreAllMocks();
  endSession();
});

describe("session", () => {
  it("notes that this tab signed in, and forgets it", () => {
    startSession(TEST_USER);
    expect(isSignedIn()).toBe(true);

    endSession();
    expect(isSignedIn()).toBe(false);
  });

  it("never keeps a token where page scripts could read it (#102)", () => {
    startSession(TEST_USER);

    // Only the note and the account: nothing a script could replay.
    const stored = Object.keys(sessionStorage).map((key) => `${key}=${sessionStorage.getItem(key)}`);
    expect(stored.join(" ")).not.toMatch(/token|eyJ/i);
    expect(Object.keys(localStorage)).toEqual([]);
    expect(document.cookie).toBe("");
  });

  it("removes a token an older version of the app left behind", () => {
    sessionStorage.setItem("voiceguard.token", "old-token");

    restorePostHogIdentity();

    expect(sessionStorage.getItem("voiceguard.token")).toBeNull();
  });

  it("still works when the browser blocks storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });

    expect(() => startSession(TEST_USER)).not.toThrow();
    expect(isSignedIn()).toBe(true);
  });
});

describe("requests to the API", () => {
  it("send the sign-in cookie and never a token header", () => {
    startSession(TEST_USER);

    expect(api.defaults.withCredentials).toBe(true);
    expect(api.defaults.headers.common.Authorization).toBeUndefined();
    // No interceptor adds one either.
    expect((api.interceptors.request as unknown as { handlers: unknown[] }).handlers.filter(Boolean)).toEqual([]);
  });
});
