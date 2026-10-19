import { api } from "./client";

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
