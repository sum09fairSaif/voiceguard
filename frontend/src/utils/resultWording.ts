import type { VerifyResult } from "../api/verify";
import type { CheckState } from "../components/CheckStatusIcon";
import type { EmblemTone } from "../components/ResultEmblem";

// Each check's outcome is shown only when the server sends it (backend
// VERIFY_CHECK_DETAILS, off by default, #112). Otherwise the screen says only
// the outcome and what to do next: naming the check that failed would help
// someone tune a replay or voice clone.

export type CheckRow = {
  label: string;
  state: CheckState;
  detail: string;
};

export type ResultView = {
  tone: EmblemTone;
  eyebrow: string;
  title: string;
  subtitle: string;
  // A line under the subtitle about attempts left, after a rejection only.
  note?: string;
  // Empty when the server hides the check details.
  checks: CheckRow[];
  // "home" opens the account (approved only); "done" goes back to the start;
  // "retry" gets a fresh passage.
  action: "home" | "done" | "retry";
  actionLabel: string;
  // Voice checks are paused: offer recording a new Voice ID (#20).
  offerRecovery?: boolean;
};

function checkRows(result: VerifyResult): CheckRow[] {
  const { content, identity, liveness } = result;
  if (content === null || identity === null || liveness === null) return [];
  const words = `${content.matched}/${content.total} words`;
  return [
    { label: "Words", state: content.passed ? "passed" : "failed", detail: words },
    {
      label: "Voice",
      state: identity === "passed" ? "passed" : identity === "failed" ? "failed" : "pending",
      detail: identity === "passed" ? "Matched" : identity === "failed" ? "Didn’t match" : "Not set up yet",
    },
    {
      label: "Live speaker",
      state: liveness === "passed" ? "passed" : liveness === "failed" ? "failed" : "pending",
      detail: liveness === "passed" ? "Confirmed" : liveness === "failed" ? "Not confirmed" : "Not checked yet",
    },
  ];
}

function rejectedSubtitle(result: VerifyResult): string {
  // Details hidden: the general line below, whichever check failed.
  if (result.content && !result.content.passed) {
    return "The words didn’t match the phrase. Find a quiet spot and read it again, word for word.";
  }
  if (result.identity === "failed") {
    return "Your voice didn’t match this account. Please try again in your natural voice.";
  }
  if (result.liveness === "failed") {
    return "We couldn’t confirm a live speaker. Please try again, speaking directly into your device.";
  }
  return "We couldn’t verify you this time. Please try again.";
}

// How many more rejections before voice checks pause (#141). The length of
// the pause is a server setting and the result doesn't carry it, so it isn't
// promised here; the passage screen says the exact wait if they come back early.
function attemptsNote(attemptsLeft: number): string {
  if (attemptsLeft === 1) {
    return "1 attempt left. If the next one doesn’t match, voice checks will pause for a while.";
  }
  return `${attemptsLeft} attempts left.`;
}

// Turns the server's answer into plain words for the screen. The server's own
// `reason` is never shown as-is.
export function describeResult(result: VerifyResult): ResultView {
  const checks = checkRows(result);
  switch (result.decision) {
    case "approved":
      return {
        tone: "success",
        eyebrow: "Identity confirmed",
        title: "You’re in. Securely.",
        subtitle: "A more personal way to protect what matters to you.",
        checks,
        // Figma 19:371's button. The API has swapped in the voice-verified
        // cookie that opens the account (#102); the page never sees it.
        action: "home",
        actionLabel: "Continue to home",
      };
    case "rejected":
      if (result.fallback_required) {
        // That was the last attempt: a new passage would be refused now.
        return {
          tone: "failure",
          eyebrow: "Not verified",
          title: "Voice checks are paused.",
          subtitle:
            "That didn’t match, and it was the last attempt for now. To keep your account safe, voice checks are paused for a while. Please come back and try again later, or record a new Voice ID.",
          checks,
          action: "done",
          actionLabel: "Done",
          offerRecovery: true,
        };
      }
      return {
        tone: "failure",
        eyebrow: "Not verified",
        title: "That didn’t match.",
        subtitle: rejectedSubtitle(result),
        // Left out if the server didn't say (a backend from before #141).
        note: typeof result.attempts_left === "number" ? attemptsNote(result.attempts_left) : undefined,
        checks,
        action: "retry",
        actionLabel: "Try again",
      };
    case "incomplete":
      return {
        tone: "partial",
        eyebrow: "Partly verified",
        title: "Almost there.",
        // Only ever an account without Voice ID: words alone can't confirm
        // someone. Says nothing about the words, so it reads the same with
        // the details hidden.
        subtitle: "Your Voice ID isn’t set up yet, so we couldn’t finish confirming it’s you.",
        checks,
        action: "retry",
        actionLabel: "Try again",
      };
  }
}
