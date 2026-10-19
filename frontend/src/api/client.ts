import axios from "axios";
import { getToken } from "./session";

// Vercel's VITE_API_BASE_URL ends in "/", which would turn "/api/..." into
// "//api/...", so trailing slashes are dropped.
export function normalizeBaseUrl(raw: string | undefined): string {
  return (raw ?? "").trim().replace(/\/+$/, "");
}

export const api = axios.create({
  baseURL: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL),
  // Render's free tier can take close to a minute to wake up.
  timeout: 60_000,
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
