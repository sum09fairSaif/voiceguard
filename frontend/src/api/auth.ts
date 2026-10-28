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
  access_token: string;
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
