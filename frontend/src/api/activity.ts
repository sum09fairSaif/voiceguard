import { api } from "./client";

// The security events a user is shown of their own (backend audit.SHOWN_TO_USER).
export type ActivityKind =
  | "signup"
  | "email_verified"
  | "login_succeeded"
  | "login_failed"
  | "login_locked"
  | "logout"
  | "enrolled"
  | "voice_check_approved"
  | "voice_check_rejected"
  | "voice_check_incomplete"
  | "voice_checks_paused"
  | "password_reset_requested"
  | "password_reset";

export type ActivityEvent = { kind: ActivityKind; at: string };

// The signed-in user's own events from the last 30 days, newest first: what
// happened and when, never why. Like the account summary, only for a
// voice-verified session (403 for a password alone).
export async function getActivity(): Promise<ActivityEvent[]> {
  const { data } = await api.get<{ events: ActivityEvent[] }>("/api/activity");
  return data.events;
}
