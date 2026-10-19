import { api } from "./client";

export type Challenge = {
  attempt_id: string;
  passage: string;
  // UTC, e.g. "2026-10-19T03:02:00Z". Only ever compared with Date.now(),
  // never shown as-is.
  expires_at: string;
};

// Each call starts a new attempt and cancels any earlier unused passage,
// so only the newest attempt_id is ever valid.
export async function requestChallenge(): Promise<Challenge> {
  const { data } = await api.post<Challenge>("/api/challenge");
  return data;
}
