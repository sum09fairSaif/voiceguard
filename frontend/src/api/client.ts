import axios from "axios";

// Vercel's VITE_API_BASE_URL ends in "/", which would turn "/api/..." into
// "//api/...", so trailing slashes are dropped.
export function normalizeBaseUrl(raw: string | undefined): string {
  return (raw ?? "").trim().replace(/\/+$/, "");
}

const LOCAL_API = "http://localhost:8000";
const PRODUCTION_API = "https://voiceguard-83cj.onrender.com";

// If VITE_API_BASE_URL isn't set (e.g. a deployment missing the setting),
// fall back to the right backend instead of sending requests to the
// frontend's own address: the local backend in development, Render otherwise.
export function resolveBaseUrl(raw: string | undefined, isDev: boolean): string {
  return normalizeBaseUrl(raw) || (isDev ? LOCAL_API : PRODUCTION_API);
}

export const api = axios.create({
  baseURL: resolveBaseUrl(import.meta.env.VITE_API_BASE_URL, import.meta.env.DEV),
  // Render's free tier can take close to a minute to wake up.
  timeout: 60_000,
  // Sends the sign-in cookie the API set (#102). The page never sees the
  // token: no Authorization header is added. The browser only sends the
  // cookie when the app and API share a site (app.<domain> and
  // api.<domain>), so VITE_API_BASE_URL must point at api.<domain>.
  withCredentials: true,
});
