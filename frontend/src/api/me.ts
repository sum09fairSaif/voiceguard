import { api } from "./client";

// The account summary. The server only answers it for a voice-verified
// session (password and an approved voice check): 403 for a password alone.
export type Me = {
  full_name: string;
  email: string;
  created_at: string;
  enrolled_at: string | null;
  // The voice-verified sign-in before this one; null on the first.
  previous_sign_in_at: string | null;
};

export async function getMe(): Promise<Me> {
  const { data } = await api.get<Me>("/api/me");
  return data;
}
