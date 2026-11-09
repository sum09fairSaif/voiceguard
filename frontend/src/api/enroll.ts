import { isAxiosError } from "axios";
import { api } from "./client";
import { describeApiError } from "./errors";

export type Enrollment = {
  status: "not_started" | "in_progress" | "enrolled";
  samples_accepted: number;
  samples_required: number;
  // A fresh phrase to read for the next sample on every call; null once enrolled.
  prompt: string | null;
};

export async function getEnrollment(): Promise<Enrollment> {
  const { data } = await api.get<Enrollment>("/api/enroll");
  return data;
}

// Sends one sample. The first one can take a while: the voice model service
// may be waking up as well as Render.
export async function addSample(audio: Blob): Promise<Enrollment> {
  const form = new FormData();
  // The server ignores the filename and reads the format from the type.
  form.append("audio", audio, "sample");
  const { data } = await api.post<Enrollment>("/api/enroll/samples", form, { timeout: 90_000 });
  return data;
}

// Throws away the samples accepted so far. A finished voiceprint stays.
export async function startOver(): Promise<Enrollment> {
  const { data } = await api.delete<Enrollment>("/api/enroll/samples");
  return data;
}

export const ENROLL_MESSAGES = {
  tooShort: "We couldn't hear enough of that one. Read the whole phrase clearly, close to your microphone, and try again.",
  tooLoud: "That one sounded distorted, as if it was too loud. Move a little further from your microphone and try again.",
  inconsistent:
    "That one didn't sound quite like your other samples. Record it again in the same quiet place. If it keeps happening, start over.",
  unreadable: "We couldn't make out that recording. Please record it again.",
  rejected: "That recording didn't work. Please record it again.",
  tooLong: "That recording is too long. Please read just the phrase.",
  format: "Your browser recorded audio in a format we can't use. Please try Chrome or Safari.",
};

// The server says why a sample was rejected (422) in a sentence meant for the
// user. We keep what it says but word it ourselves, like every other message,
// so server text never appears on screen. There are no error codes, so the
// known reasons are recognised by a key phrase.
const REJECTION_REASONS: [RegExp, string][] = [
  [/too short|too quiet/i, ENROLL_MESSAGES.tooShort],
  [/too loud|distorted/i, ENROLL_MESSAGES.tooLoud],
  [/doesn't sound like|does not sound like/i, ENROLL_MESSAGES.inconsistent],
  [/couldn't read|could not read/i, ENROLL_MESSAGES.unreadable],
];

export function isAlreadyEnrolled(error: unknown): boolean {
  return isAxiosError(error) && error.response?.status === 409;
}

export function describeEnrollError(error: unknown): string {
  if (isAxiosError(error) && error.response?.status === 422) {
    const detail = error.response.data?.detail;
    if (typeof detail === "string") {
      for (const [pattern, message] of REJECTION_REASONS) {
        if (pattern.test(detail)) return message;
      }
    }
    return ENROLL_MESSAGES.rejected;
  }
  return describeApiError(error, { 413: ENROLL_MESSAGES.tooLong, 415: ENROLL_MESSAGES.format });
}
