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

function directives(policy: string): Record<string, string[]> {
  return Object.fromEntries(
    policy
      .split(";")
      .map((part) => part.trim().split(/\s+/))
      .filter((words) => words[0])
      .map(([name, ...sources]) => [name, sources]),
  );
}

describe("security headers in vercel.json", () => {
  it("apply to every page", () => {
    expect(everyPage).toBeDefined();
  });

  it("limit what the page may load and run to our own origin and the API", () => {
    const csp = directives(header("Content-Security-Policy"));

    expect(csp["default-src"]).toEqual(["'self'"]);
    expect(csp["script-src"]).toEqual(["'self'"]);
    expect(csp["style-src"]).toEqual(["'self'"]);
    expect(csp["img-src"]).toEqual(["'self'", "data:"]);
    expect(csp["connect-src"]).toEqual(["'self'", "https://voiceguard-83cj.onrender.com"]);
    expect(csp["object-src"]).toEqual(["'none'"]);
    expect(csp["base-uri"]).toEqual(["'self'"]);
    expect(csp["form-action"]).toEqual(["'self'"]);
    expect(csp["frame-ancestors"]).toEqual(["'none'"]);
  });

  it("never allows inline or evaluated scripts", () => {
    const policy = header("Content-Security-Policy");

    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).not.toMatch(/\*/);
  });

  it("allow the microphone only on our own pages and turn off what we don't use", () => {
    const permissions = header("Permissions-Policy");

    expect(permissions).toContain("microphone=(self)");
    for (const feature of ["camera=()", "geolocation=()", "payment=()"]) {
      expect(permissions).toContain(feature);
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
