import { describe, expect, it } from "vitest";
import { formatCountdown, parseServerTime, secondsLeft } from "./countdown";

const NOW = Date.parse("2026-10-19T03:00:00Z");

describe("parseServerTime", () => {
  it("reads UTC times with a Z or an offset", () => {
    expect(parseServerTime("2026-10-19T03:02:00Z")).toBe(Date.parse("2026-10-19T03:02:00Z"));
    expect(parseServerTime("2026-10-19T03:02:00+00:00")).toBe(Date.parse("2026-10-19T03:02:00Z"));
  });

  it("treats a time with no timezone as UTC, not local time", () => {
    expect(parseServerTime("2026-10-19T03:02:00")).toBe(Date.parse("2026-10-19T03:02:00Z"));
    expect(parseServerTime("2026-10-19T03:02:00.123456")).toBe(Date.parse("2026-10-19T03:02:00.123Z"));
  });
});

describe("secondsLeft", () => {
  it("counts down to the expiry time", () => {
    expect(secondsLeft("2026-10-19T03:02:00Z", NOW)).toBe(120);
  });

  it("rounds part-seconds up, so 0:00 only shows once it has really expired", () => {
    expect(secondsLeft("2026-10-19T03:00:00.400Z", NOW)).toBe(1);
  });

  it("never goes below zero", () => {
    expect(secondsLeft("2026-10-19T02:59:00Z", NOW)).toBe(0);
  });

  it("treats an unreadable time as expired", () => {
    expect(secondsLeft("not a time", NOW)).toBe(0);
  });
});

describe("formatCountdown", () => {
  it.each([
    [120, "2:00"],
    [65, "1:05"],
    [9, "0:09"],
    [0, "0:00"],
  ])("shows %i seconds as %s", (seconds, text) => {
    expect(formatCountdown(seconds)).toBe(text);
  });
});
