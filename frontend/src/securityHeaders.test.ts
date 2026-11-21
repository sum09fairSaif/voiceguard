import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// vercel.json is what the live site sends. This stops the headers being
// dropped or loosened by accident.
type Header = { key: string; value: string };
const config = JSON.parse(readFileSync(resolve(__dirname, "../vercel.json"), "utf8")) as {
  headers: { source: string; headers: Header[] }[];
};

const everyPage = config.headers.find((rule) => rule.source === "/(.*)");
const header = (key: string) => everyPage?.headers.find((h) => h.key === key)?.value ?? "";

// Browsers enforce the first copy of a repeated directive, so a repeat could
// quietly loosen the policy: fail on one rather than read past it.
function directives(policy: string): Record<string, string[]> {
  const parsed: Record<string, string[]> = {};
  for (const part of policy.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (!name) continue;
    if (name in parsed) throw new Error(`CSP directive repeated: ${name}`);
    parsed[name] = sources;
  }
  return parsed;
}

// "microphone=(self), camera=()" → { microphone: "(self)", camera: "()" },
// so a check can't be fooled by a look-alike name such as "x-camera".
function features(policy: string): Record<string, string> {
  const parsed: Record<string, string> = {};
  for (const part of policy.split(",")) {
    const [name, allowlist] = part.trim().split("=");
    if (!name) continue;
    if (name in parsed) throw new Error(`Permissions-Policy feature repeated: ${name}`);
    parsed[name] = allowlist ?? "";
  }
  return parsed;
}

// Our PostHog project is in the US region.
const POSTHOG_API = "https://us.i.posthog.com";
const POSTHOG_ASSETS = "https://us-assets.i.posthog.com";

describe("security headers in vercel.json", () => {
  it("apply to every page", () => {
    expect(everyPage).toBeDefined();
  });

  it("limit what the page may load and run to our own origin, the API and PostHog", () => {
    const csp = directives(header("Content-Security-Policy"));

    expect(csp["default-src"]).toEqual(["'self'"]);
    // PostHog lazy-loads its extras (e.g. the session recorder) from its asset host.
    expect(csp["script-src"]).toEqual(["'self'", POSTHOG_ASSETS]);
    expect(csp["style-src"]).toEqual(["'self'"]);
    expect(csp["img-src"]).toEqual(["'self'", "data:"]);
    expect(csp["font-src"]).toEqual(["'self'"]);
    expect(csp["media-src"]).toEqual(["'self'"]);
    expect(csp["connect-src"]).toEqual([
      "'self'",
      // Our own domain (#193), and Render's address until the app has moved.
      "https://api.get-voiceguard.tech",
      "https://voiceguard-83cj.onrender.com",
      POSTHOG_API,
      POSTHOG_ASSETS,
    ]);
    expect(csp["object-src"]).toEqual(["'none'"]);
    expect(csp["base-uri"]).toEqual(["'self'"]);
    expect(csp["form-action"]).toEqual(["'self'"]);
    expect(csp["frame-ancestors"]).toEqual(["'none'"]);
    expect(csp["upgrade-insecure-requests"]).toEqual([]);
  });

  it("rejects a repeated directive, which browsers would read the first copy of", () => {
    expect(() => directives("script-src 'self'; script-src *")).toThrow("repeated");
    expect(() => features("camera=(), camera=(*)")).toThrow("repeated");
  });

  it("never allows inline or evaluated scripts", () => {
    const policy = header("Content-Security-Policy");

    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).not.toMatch(/\*/);
  });

  it("allow the microphone only on our own pages and turn off what we don't use", () => {
    const allowed = features(header("Permissions-Policy"));

    expect(allowed.microphone).toBe("(self)");
    for (const feature of ["camera", "geolocation", "payment", "usb"]) {
      expect(allowed[feature]).toBe("()");
    }
  });

  it("stop content sniffing, framing and full referrers", () => {
    expect(header("X-Content-Type-Options")).toBe("nosniff");
    expect(header("X-Frame-Options")).toBe("DENY");
    expect(header("Referrer-Policy")).toBe("strict-origin-when-cross-origin");
  });

  it("keep sending every route to the app", () => {
    expect(config).toMatchObject({ rewrites: [{ source: "/(.*)", destination: "/index.html" }] });
  });
});
