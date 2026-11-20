import { api } from "./client";
import type { SignupResponse } from "./auth";

// Confirming the email address at signup (#110). Signup already emails the
// first code; these ask for another and check one.

export async function sendEmailCode(): Promise<void> {
  await api.post("/api/auth/email/code");
}

export type EmailVerifiedResponse = { user: SignupResponse["user"] };

export async function confirmEmail(code: string): Promise<EmailVerifiedResponse> {
  const { data } = await api.post<EmailVerifiedResponse>("/api/auth/email/verify", { code });
  return data;
}

// The code is six digits; people often paste it with spaces.
export function normalizeCode(raw: string): string {
  return raw.replace(/\s+/g, "");
}

export function isWellFormedCode(code: string): boolean {
  return /^\d{6}$/.test(code);
}
