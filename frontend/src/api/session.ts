import posthog, { isPostHogConfigured } from "../posthog";

const TOKEN_KEY = "voiceguard.token";
const USER_KEY = "voiceguard.user";

export type AuthenticatedUser = {
  id: string;
  full_name: string;
  email: string;
};

// The token and the identity needed to restore analytics live in sessionStorage,
// so they're gone when the tab closes. Storage can be unavailable (e.g. some
// private-browsing modes), so we keep in-memory copies too and never let storage
// errors crash the app.
let memoryToken: string | null = null;
let memoryUser: AuthenticatedUser | null = null;

function isAuthenticatedUser(value: unknown): value is AuthenticatedUser {
  if (!value || typeof value !== "object") return false;
  const user = value as Record<string, unknown>;
  return typeof user.id === "string" && typeof user.full_name === "string" && typeof user.email === "string";
}

function getStoredUser(): AuthenticatedUser | null {
  try {
    const saved = sessionStorage.getItem(USER_KEY);
    if (!saved) return memoryUser;
    const user: unknown = JSON.parse(saved);
    return isAuthenticatedUser(user) ? user : memoryUser;
  } catch {
    return memoryUser;
  }
}

function identify(user: AuthenticatedUser): void {
  if (!isPostHogConfigured) return;
  // The opaque account id only: no email or name goes to analytics.
  posthog.identify(user.id);
}

export function saveToken(token: string, user?: AuthenticatedUser): void {
  const previousUser = getStoredUser();
  memoryToken = token;
  if (user) memoryUser = user;
  try {
    // User first: if the token write then fails, nothing restores a session
    // for the wrong account.
    if (user) sessionStorage.setItem(USER_KEY, JSON.stringify(user));
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // The in-memory copies still work for this page load.
  }

  if (user) {
    if (previousUser && previousUser.id !== user.id && isPostHogConfigured) posthog.reset();
    identify(user);
    if (isPostHogConfigured) posthog.logger.info("authenticated session established");
  }
}

// The signed-in account as saved at sign-in, e.g. to show its email address.
export function getSignedInUser(): AuthenticatedUser | null {
  return getStoredUser();
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

// Call once when the browser starts so a session that survives a page refresh
// remains associated with the stable account id.
export function restorePostHogIdentity(): void {
  if (getToken()) {
    const user = getStoredUser();
    if (user) identify(user);
  }
}

export function clearToken(): void {
  const hadSession = getToken() !== null;
  memoryToken = null;
  memoryUser = null;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
  if (hadSession && isPostHogConfigured) posthog.reset();
}
