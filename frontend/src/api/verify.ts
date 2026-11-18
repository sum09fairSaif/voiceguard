import { isAxiosError } from "axios";
import { api } from "./client";
import { describeApiError } from "./errors";

export type VerifyResult = {
  decision: "approved" | "rejected" | "incomplete";
  reason: string;
  content: { passed: boolean; score: number; matched: number; total: number };
  identity: "passed" | "failed" | "not_enrolled";
  // Only "not_checked" until the liveness check (#17) exists; the other
  // values are handled already so the result screen needs no change then.
  liveness: "passed" | "failed" | "not_checked";
  // Rejections left before voice checks pause. Back to the maximum after an
  // approval; an "incomplete" doesn't lower it. Optional: a backend from
  // before #141 doesn't send these, and the screen then leaves them out.
  attempts_left?: number;
  // True when this rejection used the last attempt, so checks are paused now.
  fallback_required?: boolean;
  // Not used: on approval the API sets the voice-verified token as a
  // cookie the page can't read (#102). Sent in the body too only while the
  // backend's TOKEN_IN_RESPONSE_BODY is on, for the change-over.
  access_token?: string | null;
};

// What the voice check's error statuses mean for the person on screen. Used as
// overrides for describeApiError; anything else falls back to its messages.
export const VERIFY_MESSAGES: Partial<Record<number, string>> = {
  400: "This phrase has expired or was already used. Get a new phrase and try again.",
  413: "That recording is too long. Please read just the phrase.",
  415: "Your browser recorded audio in a format we can't use. Please try Chrome or Safari.",
  422: "We couldn't make out the recording. Get a new phrase and record again.",
};

// After 3 rejections the server pauses voice checks for this account (423 on
// both a new passage and a submit) and says how long in Retry-After. This is
// not the sign-in lockout (also 423, handled in auth.ts): the voice screens
// word it themselves, like every other message.
export function pausedMessage(retryAfterSeconds: number | undefined): string {
  if (!retryAfterSeconds || retryAfterSeconds <= 0) {
    return "Voice checks are paused after too many failed attempts. Please try again later.";
  }
  const minutes = Math.ceil(retryAfterSeconds / 60);
  return `Voice checks are paused after too many failed attempts. Please try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}

// Shown once a pause is over, so the screen can offer a new phrase again.
export const AVAILABLE_AGAIN = "Voice checks are available again. Get a new phrase to try again.";

// How long a pause lasts, from Retry-After; undefined if the server didn't say.
export function pauseSeconds(error: unknown): number | undefined {
  if (!isAxiosError(error)) return undefined;
  const seconds = Number(error.response?.headers["retry-after"]);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : undefined;
}

export function isVoiceCheckPaused(error: unknown): boolean {
  return isAxiosError(error) && error.response?.status === 423;
}

// The message for any error from a passage request or a submit.
export function describeVoiceCheckError(
  error: unknown,
  overrides: Partial<Record<number, string>> = VERIFY_MESSAGES,
): string {
  if (isAxiosError(error) && isVoiceCheckPaused(error)) {
    return pausedMessage(pauseSeconds(error));
  }
  return describeApiError(error, overrides);
}

// Sends the recording with the attempt it answers. Each attempt can be checked
// once: the server uses it up before transcribing, so any retry needs a new
// passage.
export async function submitAttempt(audio: Blob, attemptId: string): Promise<VerifyResult> {
  const form = new FormData();
  form.append("attempt_id", attemptId);
  // The server ignores the filename and reads the format from the type.
  form.append("audio", audio, "attempt");
  // Speech-to-text and the voice model can take a while, on top of Render waking up.
  const { data } = await api.post<VerifyResult>("/api/verify", form, { timeout: 90_000 });
  return data;
}
