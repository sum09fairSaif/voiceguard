import { describe, expect, it } from "vitest";
import type { VerifyResult } from "../api/verify";
import { describeResult } from "./resultWording";

function result(overrides: Partial<VerifyResult> = {}): VerifyResult {
  return {
    decision: "incomplete",
    reason: "server text that must not be shown",
    content: { passed: true, score: 1, matched: 6, total: 6 },
    identity: "not_enrolled",
    liveness: "not_checked",
    ...overrides,
  };
}

describe("describeResult", () => {
  it("confirms access for an approved check", () => {
    const view = describeResult(result({ decision: "approved", identity: "passed", liveness: "passed" }));

    expect(view).toMatchObject({ tone: "success", title: "You’re in. Securely.", action: "done", actionLabel: "Done" });
    expect(view.checks.map((check) => check.state)).toEqual(["passed", "passed", "passed"]);
  });

  it("says the words were wrong when the phrase didn't match", () => {
    const view = describeResult(
      result({ decision: "rejected", content: { passed: false, score: 0.33, matched: 2, total: 6 } }),
    );

    expect(view).toMatchObject({ tone: "failure", title: "That didn’t match.", action: "retry" });
    expect(view.subtitle).toMatch(/words didn’t match/);
    expect(view.checks[0]).toEqual({ label: "Words", state: "failed", detail: "2/6 words" });
  });

  it("says the voice was wrong when the words matched but the voice didn't", () => {
    const view = describeResult(result({ decision: "rejected", identity: "failed" }));

    expect(view.subtitle).toMatch(/voice didn’t match/);
    expect(view.checks[1]).toEqual({ label: "Voice", state: "failed", detail: "Didn’t match" });
  });

  it("is ready for a failed liveness check", () => {
    const view = describeResult(result({ decision: "rejected", identity: "passed", liveness: "failed" }));

    expect(view.subtitle).toMatch(/live speaker/);
    expect(view.checks[2]).toEqual({ label: "Live speaker", state: "failed", detail: "Not confirmed" });
  });

  it("explains a partly verified result without a voiceprint", () => {
    const view = describeResult(result());

    expect(view).toMatchObject({ tone: "partial", title: "Almost there.", action: "retry" });
    expect(view.subtitle).toMatch(/once your voice is set up/);
    expect(view.checks).toEqual([
      { label: "Words", state: "passed", detail: "6/6 words" },
      { label: "Voice", state: "pending", detail: "Not set up yet" },
      { label: "Live speaker", state: "pending", detail: "Not checked yet" },
    ]);
  });

  it("explains a partly verified result when the voice matched", () => {
    const view = describeResult(result({ identity: "passed" }));

    expect(view.subtitle).toMatch(/words and voice both matched/);
    expect(view.checks[1]).toEqual({ label: "Voice", state: "passed", detail: "Matched" });
  });

  it.each(["approved", "rejected", "incomplete"] as const)("never shows the server's own text (%s)", (decision) => {
    const view = describeResult(result({ decision }));

    expect(JSON.stringify(view)).not.toContain("server text");
  });
});
