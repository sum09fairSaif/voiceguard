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
    attempts_left: 3,
    fallback_required: false,
    ...overrides,
  };
}

describe("describeResult", () => {
  it("confirms access for an approved check", () => {
    const view = describeResult(
      result({ decision: "approved", identity: "passed", liveness: "passed", access_token: "voice-verified" }),
    );

    expect(view).toMatchObject({ tone: "success", title: "You’re in. Securely.", action: "home", actionLabel: "Continue to home" });
    expect(view.checks.map((check) => check.state)).toEqual(["passed", "passed", "passed"]);
  });

  it("opens the account after an approval even with no token in the answer (#102: it's a cookie)", () => {
    const view = describeResult(result({ decision: "approved", identity: "passed", liveness: "passed" }));

    expect(view).toMatchObject({ title: "You’re in. Securely.", action: "home", actionLabel: "Continue to home" });
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

  it.each([
    [2, "2 attempts left."],
    [1, "1 attempt left. If the next one doesn’t match, voice checks will pause for a while."],
  ])("says how many attempts are left after a rejection (%i)", (attemptsLeft, note) => {
    const view = describeResult(result({ decision: "rejected", identity: "failed", attempts_left: attemptsLeft }));

    expect(view.note).toBe(note);
    expect(view.action).toBe("retry");
  });

  it("says checks are paused when that rejection used the last attempt", () => {
    const view = describeResult(
      result({ decision: "rejected", identity: "failed", attempts_left: 0, fallback_required: true }),
    );

    expect(view).toMatchObject({ tone: "failure", title: "Voice checks are paused.", action: "done" });
    expect(view.subtitle).toMatch(/last attempt/);
    expect(view.note).toBeUndefined();
  });

  it("leaves the attempts note out when the server didn't send it", () => {
    const fromOlderBackend = result({ decision: "rejected", identity: "failed" });
    delete fromOlderBackend.attempts_left;
    delete fromOlderBackend.fallback_required;

    const view = describeResult(fromOlderBackend);

    expect(view.note).toBeUndefined();
    expect(view).toMatchObject({ title: "That didn’t match.", action: "retry" });
  });

  it("gives no attempts note unless the check was rejected", () => {
    expect(describeResult(result()).note).toBeUndefined();
    expect(describeResult(result({ decision: "approved", identity: "passed", liveness: "passed" })).note).toBeUndefined();
  });

  it("explains a partly verified result without a voiceprint", () => {
    const view = describeResult(result());

    expect(view).toMatchObject({ tone: "partial", title: "Almost there.", action: "retry" });
    expect(view.subtitle).toMatch(/Voice ID isn’t set up yet/);
    expect(view.subtitle).not.toMatch(/coming soon/);
    expect(view.checks).toEqual([
      { label: "Words", state: "passed", detail: "6/6 words" },
      { label: "Voice", state: "pending", detail: "Not set up yet" },
      { label: "Live speaker", state: "pending", detail: "Not checked yet" },
    ]);
  });

  describe("with the check details hidden by the server (#112)", () => {
    const HIDDEN = { content: null, identity: null, liveness: null } as const;
    // Words that would say which check decided it.
    const NAMES_A_CHECK = /words|phrase|voice didn|voice match|live speaker|live-speaker|speaking directly/i;

    function hidden(overrides: Partial<VerifyResult> = {}) {
      return describeResult(result({ ...HIDDEN, ...overrides }));
    }

    it("confirms an approval without a breakdown", () => {
      const view = hidden({ decision: "approved", access_token: "voice-verified" });

      expect(view).toMatchObject({ tone: "success", action: "home", actionLabel: "Continue to home", checks: [] });
    });

    it("gives a rejection the general line, with the attempts left", () => {
      const view = hidden({ decision: "rejected", attempts_left: 2 });

      expect(view).toMatchObject({ tone: "failure", title: "That didn’t match.", action: "retry", checks: [] });
      expect(view.subtitle).toBe("We couldn’t verify you this time. Please try again.");
      expect(view.note).toBe("2 attempts left.");
    });

    it("still says when the last attempt paused voice checks", () => {
      const view = hidden({ decision: "rejected", attempts_left: 0, fallback_required: true });

      expect(view).toMatchObject({ title: "Voice checks are paused.", action: "done", checks: [] });
    });

    it("tells an account without Voice ID to set it up", () => {
      const view = hidden({ decision: "incomplete" });

      expect(view).toMatchObject({ tone: "partial", action: "retry", checks: [] });
      expect(view.subtitle).toMatch(/Voice ID isn’t set up yet/);
    });

    it.each(["approved", "rejected", "incomplete"] as const)("never names a check (%s)", (decision) => {
      const view = hidden({ decision, fallback_required: false });

      expect(`${view.title} ${view.subtitle} ${view.note ?? ""}`).not.toMatch(NAMES_A_CHECK);
    });
  });

  it.each(["approved", "rejected", "incomplete"] as const)("never shows the server's own text (%s)", (decision) => {
    const view = describeResult(result({ decision }));

    expect(JSON.stringify(view)).not.toContain("server text");
  });
});
