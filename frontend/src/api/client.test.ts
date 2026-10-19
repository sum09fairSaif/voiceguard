import { describe, expect, it } from "vitest";
import { normalizeBaseUrl } from "./client";

describe("normalizeBaseUrl", () => {
  it("drops the trailing slash Vercel's value ends with", () => {
    expect(normalizeBaseUrl("https://voiceguard-83cj.onrender.com/")).toBe(
      "https://voiceguard-83cj.onrender.com",
    );
  });

  it("drops several trailing slashes and surrounding spaces", () => {
    expect(normalizeBaseUrl("  http://localhost:8000///  ")).toBe("http://localhost:8000");
  });

  it("leaves a clean URL alone", () => {
    expect(normalizeBaseUrl("http://localhost:8000")).toBe("http://localhost:8000");
  });

  it("treats a missing value as empty", () => {
    expect(normalizeBaseUrl(undefined)).toBe("");
  });
});
