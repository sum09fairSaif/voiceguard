import { api } from "./client";
import type { SignupResponse } from "./auth";

// Confirming the email address at signup (#110). While confirmation is on,
// signup gives no sign-in and never says whether the address already has an
// account (#111): the session starts here, with the address and the emailed
// code. Both calls work by address, without a token.

export async function sendEmailCode(email: string): Promise<void> {
  // Always the same answer, whether or not anything was sent.
  await api.post("/api/auth/email/code", { email });
}

// Like sign-in: the confirmed account and a fresh token.
export async function confirmEmail(email: string, code: string): Promise<SignupResponse> {
  const { data } = await api.post<SignupResponse>("/api/auth/email/verify", { email, code });
  return data;
}

// The code is six digits; people often paste it with spaces.
export function normalizeCode(raw: string): string {
  return raw.replace(/\s+/g, "");
}

export function isWellFormedCode(code: string): boolean {
  return /^\d{6}$/.test(code);
}
