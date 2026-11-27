import { api } from "./client";

// Forgot password (#109). The server answers the same way whether or not
// the address has an account, so the screen can't tell either.
export async function requestPasswordReset(email: string): Promise<void> {
  await api.post("/api/auth/password-reset", { email });
}

// Sets the new password with the token from the emailed link. On success
// every session the account had is ended, this one included, so the user
// signs in again.
export async function confirmPasswordReset(token: string, password: string): Promise<void> {
  await api.post("/api/auth/password-reset/confirm", { token, password });
}

// The link's token comes after "#token=" (backend/password_reset.py): that
// part of an address never reaches a server, so it stays out of logs.
export function tokenFromHash(hash: string): string | null {
  const token = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return token && token.trim() ? token.trim() : null;
}
