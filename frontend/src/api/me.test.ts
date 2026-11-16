import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";
import { getMe } from "./me";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("getMe", () => {
  it("reads the account summary", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: { email: "sam@example.com" } });

    await expect(getMe()).resolves.toEqual({ email: "sam@example.com" });
    expect(get).toHaveBeenCalledWith("/api/me");
  });
});
