import { afterEach, describe, expect, it, vi } from "vitest";
import { requestChallenge } from "./challenge";
import { api } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("requestChallenge", () => {
  it("asks the backend for a new passage and returns it", async () => {
    const challenge = { attempt_id: "a1", passage: "quilt tiger ocean pebble winter planet", expires_at: "2026-10-19T03:02:00Z" };
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: challenge });

    await expect(requestChallenge()).resolves.toEqual(challenge);
    expect(post).toHaveBeenCalledWith("/api/challenge");
  });
});
