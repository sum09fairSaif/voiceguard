import { afterEach, describe, expect, it, vi } from "vitest";
import { clearToken, getToken, saveToken } from "./session";

afterEach(() => {
  vi.restoreAllMocks();
  clearToken();
});

describe("session token", () => {
  it("is saved, read back and cleared", () => {
    saveToken("token-123");
    expect(getToken()).toBe("token-123");
    expect(sessionStorage.getItem("voiceguard.token")).toBe("token-123");

    clearToken();
    expect(getToken()).toBeNull();
  });

  it("still works when the browser blocks storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });

    expect(() => saveToken("token-456")).not.toThrow();
    expect(getToken()).toBe("token-456");
  });
});
