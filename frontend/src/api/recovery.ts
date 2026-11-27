import { api } from "./client";

// Recording a new Voice ID when the voice check keeps failing (#20). Both
// calls use the signed-in session (the password); the code goes to the
// account's own address, so neither takes an email.

// Only while voice checks are paused after failed tries (409 otherwise).
export async function requestRecoveryCode(): Promise<void> {
  await api.post("/api/recovery/code");
}

// A correct code lets this session record a new Voice ID for a while.
export async function confirmRecoveryCode(code: string): Promise<{ enroll_minutes: number }> {
  const { data } = await api.post<{ enroll_minutes: number }>("/api/recovery/verify", { code });
  return data;
}
