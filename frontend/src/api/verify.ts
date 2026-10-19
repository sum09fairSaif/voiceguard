import { api } from "./client";

export type VerifyResult = {
  decision: "approved" | "rejected" | "incomplete";
  reason: string;
  content: { passed: boolean; score: number; matched: number; total: number };
  identity: "passed" | "failed" | "not_enrolled";
  // Only "not_checked" until the liveness check (#17) exists; the other
  // values are handled already so the result screen needs no change then.
  liveness: "passed" | "failed" | "not_checked";
};

// What the voice check's error statuses mean for the person on screen. Used as
// overrides for describeApiError; anything else falls back to its messages.
export const VERIFY_MESSAGES: Partial<Record<number, string>> = {
  400: "This phrase has expired or was already used. Get a new phrase and try again.",
  413: "That recording is too long. Please read just the phrase.",
  415: "Your browser recorded audio in a format we can't use. Please try Chrome or Safari.",
  422: "We couldn't make out the recording. Get a new phrase and record again.",
};

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
