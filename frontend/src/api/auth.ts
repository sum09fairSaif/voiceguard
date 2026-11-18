import { isAxiosError } from "axios";
import { api } from "./client";
import { describeApiError } from "./errors";

export type SignupRequest = {
  full_name: string;
  email: string;
  password: string;
};

export type SignupResponse = {
  user: {
    id: string;
    full_name: string;
    email: string;
    created_at: string;
  };
  // Not used: the token is set as a cookie the page can't read (#102).
  // Sent in the body too only while the backend's TOKEN_IN_RESPONSE_BODY is
  // on, for the change-over; null after that.
  access_token?: string | null;
  token_type: string;
};

export async function signup(body: SignupRequest): Promise<SignupResponse> {
  const { data } = await api.post<SignupResponse>("/api/auth/signup", body);
  return data;
}

export type LoginRequest = {
  email: string;
  password: string;
};

// Same shape as signup: the account and a fresh token.
export type LoginResponse = SignupResponse;

export async function logIn(body: LoginRequest): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/api/auth/login", body);
  return data;
}

// Ends this sign-in on the server: its tokens (limited and voice-verified)
// stop working everywhere, not just in this tab.
export async function logOut(): Promise<void> {
  await api.post("/api/auth/logout");
}

// The same words whether the email or the password was wrong, as the
// server does, so the screen never gives away which emails have accounts.
export const WRONG_CREDENTIALS = "The email or password is incorrect.";

// After 5 misses the server locks sign-in for a while (423) and says how long
// in the Retry-After header. We word it ourselves rather than show the
// server's text, like every other message.
export function lockedOutMessage(retryAfterSeconds: number | undefined): string {
  if (!retryAfterSeconds || retryAfterSeconds <= 0) {
    return "Too many failed sign-in attempts, so sign-in is locked for now. Please try again later.";
  }
  const minutes = Math.ceil(retryAfterSeconds / 60);
  return `Too many failed sign-in attempts, so sign-in is locked for now. Please try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}

export function describeLoginError(error: unknown): string {
  if (isAxiosError(error) && error.response?.status === 423) {
    return lockedOutMessage(Number(error.response.headers["retry-after"]));
  }
  // A 401 here means wrong credentials, not an expired session.
  return describeApiError(error, { 401: WRONG_CREDENTIALS });
}
