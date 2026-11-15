import type { VerifyResult } from "../api/verify";
import type { CheckState } from "../components/CheckStatusIcon";
import type { EmblemTone } from "../components/ResultEmblem";

// For the MVP1 demo, the result screen shows each check's outcome as proof of
// progress. The end product should show only pass or fail: saying which
// check failed helps someone tune a fake (tracked as a separate ticket).
export const SHOW_CHECK_DETAILS = true;

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
  checks: CheckRow[];
  // "done" goes back to the start; "retry" gets a fresh passage.
  action: "done" | "retry";
  actionLabel: string;
};

function checkRows(result: VerifyResult): CheckRow[] {
  const { content, identity, liveness } = result;
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
  if (!result.content.passed) {
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
        action: "done",
        actionLabel: "Done",
      };
    case "rejected":
      if (result.fallback_required) {
        // That was the last attempt: a new passage would be refused now.
        return {
          tone: "failure",
          eyebrow: "Not verified",
          title: "Voice checks are paused.",
          subtitle:
            "That didn’t match, and it was the last attempt for now. To keep your account safe, voice checks are paused for a while. Please come back and try again later.",
          checks,
          action: "done",
          actionLabel: "Done",
        };
      }
      return {
        tone: "failure",
        eyebrow: "Not verified",
        title: "That didn’t match.",
        subtitle: rejectedSubtitle(result),
        note: attemptsNote(result.attempts_left),
        checks,
        action: "retry",
        actionLabel: "Try again",
      };
    case "incomplete":
      return {
        tone: "partial",
        eyebrow: "Partly verified",
        title: "Almost there.",
        subtitle:
          result.identity === "passed"
            ? "Your words and voice both matched. The live-speaker check is coming soon, so we can’t fully confirm you yet."
            : "You read the phrase correctly. Voice matching starts once your voice is set up, and the live-speaker check is coming soon.",
        checks,
        action: "retry",
        actionLabel: "Try again",
      };
  }
}
