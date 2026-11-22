import { describe, expect, it } from "vitest";
import { normalizeBaseUrl, resolveBaseUrl } from "./client";

describe("normalizeBaseUrl", () => {
  it("drops the trailing slash Vercel's value ends with", () => {
    expect(normalizeBaseUrl("https://api.get-voiceguard.tech/")).toBe("https://api.get-voiceguard.tech");
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

describe("resolveBaseUrl", () => {
  it("uses the configured URL when there is one", () => {
    expect(resolveBaseUrl("https://example.com/", false)).toBe("https://example.com");
  });

  it("falls back to the local backend in development", () => {
    expect(resolveBaseUrl(undefined, true)).toBe("http://localhost:8000");
  });

  it("falls back to the live API on our own domain in a deployed build", () => {
    expect(resolveBaseUrl("", false)).toBe("https://api.get-voiceguard.tech");
    expect(resolveBaseUrl("   ", false)).toBe("https://api.get-voiceguard.tech");
  });
});
