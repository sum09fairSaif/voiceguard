import { isAxiosError } from "axios";

export const MESSAGES = {
  network: "Can't reach VoiceGuard. Check your connection and try again.",
  invalid: "Some details aren't valid. Check the form and try again.",
  signedOut: "Your session has ended. Please create an account or sign in again.",
  unavailable: "VoiceGuard is temporarily unavailable. Please try again shortly.",
  unknown: "Something went wrong. Please try again.",
};

// Parts of VoiceGuard can be paused for a while (backend/switches.py); the
// server names which, and we say it in our own words.
export const PAUSED_MESSAGES: Record<string, string> = {
  signups: "Creating new accounts is paused for now. Please try again later.",
  voice_checks: "Voice checks are paused for now. Please try again later.",
  enrollment: "Setting up a Voice ID is paused for now. Please try again later.",
};

function tooManyAttempts(retryAfterSeconds: number | undefined): string {
  if (!retryAfterSeconds || retryAfterSeconds <= 0) {
    return "Too many attempts. Please wait a while and try again.";
  }
  const minutes = Math.ceil(retryAfterSeconds / 60);
  return `Too many attempts. Please try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}

// Turns any API error into a message we wrote ourselves. Server text is never
// shown as-is, so nothing internal can leak onto the screen. Screens can
// override the message for a status they understand better (e.g. 409 on signup).
export function describeApiError(
  error: unknown,
  overrides: Partial<Record<number, string>> = {},
): string {
  if (!isAxiosError(error)) return MESSAGES.unknown;
  // No response at all: offline, blocked, or timed out.
  if (!error.response) return MESSAGES.network;

  const { status, headers } = error.response;
  const override = overrides[status];
  if (override) return override;

  switch (status) {
    case 401:
      return MESSAGES.signedOut;
    case 422:
      return MESSAGES.invalid;
    case 429:
      return tooManyAttempts(Number(headers["retry-after"]));
    case 503: {
      const paused = error.response.data?.paused;
      return (typeof paused === "string" && PAUSED_MESSAGES[paused]) || MESSAGES.unavailable;
    }
    default:
      return MESSAGES.unknown;
  }
}

// For a 422, the names of the form fields the server rejected (the backend
// says which field, never echoing the value back).
export function invalidFields(error: unknown): string[] {
  if (!isAxiosError(error) || error.response?.status !== 422) return [];
  const detail = error.response.data?.detail;
  if (!Array.isArray(detail)) return [];
  return detail
    .map((item) => (Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : undefined))
    .filter((field): field is string => typeof field === "string");
}
