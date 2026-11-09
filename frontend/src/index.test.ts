/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The color tokens set contrast for every screen, so one wrong value here
// makes text hard to read everywhere. These pairs are checked against the
// WCAG AA minimums: 4.5:1 for text and 3:1 for controls and graphics.

// Read from disk because Vitest turns CSS imports, even ?raw ones, into "".
const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf-8");

function token(name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`no --${name} color in index.css`);
  return match[1];
}

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => {
    const value = parseInt(hex.slice(start, start + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(first: string, second: string): number {
  const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("color contrast", () => {
  it("calculates the known extremes", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21);
    expect(contrast("#ffffff", "#ffffff")).toBeCloseTo(1);
  });

  it("keeps gold text readable on white", () => {
    expect(contrast(token("color-gold"), token("color-surface"))).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps gold text readable on the cream card", () => {
    expect(contrast(token("color-gold"), token("color-gold-soft"))).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps the filled progress segments distinct from the empty ones", () => {
    expect(contrast(token("color-gold"), token("color-track"))).toBeGreaterThanOrEqual(3);
  });

  it("keeps the edge of an input field visible on white", () => {
    expect(contrast(token("color-input-border"), token("color-surface"))).toBeGreaterThanOrEqual(3);
  });

  it("keeps the switch links and the sentence around them readable", () => {
    expect(contrast(token("color-primary"), token("color-surface"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("color-muted"), token("color-surface"))).toBeGreaterThanOrEqual(4.5);
  });
});
