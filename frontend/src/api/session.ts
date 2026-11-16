import posthog, { isPostHogConfigured } from "../posthog";

const TOKEN_KEY = "voiceguard.token";
const USER_KEY = "voiceguard.user";

type AuthenticatedUser = {
  id: string;
  full_name: string;
  email: string;
};

// The token and identity live in sessionStorage, so they're gone when the tab
// closes. Storage can be unavailable (e.g. some private-browsing modes), so we
// keep in-memory copies too and never let storage errors crash the app.
let memoryToken: string | null = null;
let memoryUser: AuthenticatedUser | null = null;

function getUser(): AuthenticatedUser | null {
  try {
    const stored = sessionStorage.getItem(USER_KEY);
    if (!stored) return memoryUser;
    const user = JSON.parse(stored) as Partial<AuthenticatedUser>;
    if (typeof user.id !== "string" || typeof user.full_name !== "string" || typeof user.email !== "string") {
      return memoryUser;
    }
    return user as AuthenticatedUser;
  } catch {
    return memoryUser;
  }
}

function identify(user: AuthenticatedUser, previousUser: AuthenticatedUser | null): void {
  if (!isPostHogConfigured) return;
  if (previousUser && previousUser.id !== user.id) posthog.reset();
  posthog.identify(user.id, { email: user.email, name: user.full_name });
}

export function saveSession(token: string, user: AuthenticatedUser): void {
  const previousUser = getUser();
  memoryToken = token;
  memoryUser = user;
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // The in-memory copies still work for this page load.
  }
  identify(user, previousUser);
}

// Retained for callers that only have a token, such as route-guard tests.
// Authentication flows use saveSession so PostHog receives a verified user id.
export function saveToken(token: string): void {
  memoryToken = token;
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // The in-memory copy still works for this page load.
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

export function restoreSessionIdentity(): void {
  const user = getUser();
  if (getToken() && user) identify(user, null);
}

export function clearToken(): void {
  if (isPostHogConfigured && (getToken() || getUser())) posthog.reset();
  memoryToken = null;
  memoryUser = null;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
}
