import posthog, { isPosthogConfigured } from "../posthog";

const TOKEN_KEY = "voiceguard.token";
const USER_KEY = "voiceguard.user";

export type AuthenticatedUser = {
  id: string;
  full_name: string;
  email: string;
};

// The session lives in sessionStorage, so it's gone when the tab closes.
// Storage can be unavailable (e.g. some private-browsing modes), so we keep
// an in-memory copy too and never let storage errors crash the app.
let memoryToken: string | null = null;
let memoryUser: AuthenticatedUser | null = null;
let restoredIdentity = false;

function identify(user: AuthenticatedUser): void {
  if (!isPosthogConfigured) return;
  posthog.identify(user.id, { email: user.email, name: user.full_name });
}

export function saveToken(token: string): void {
  memoryToken = token;
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // The in-memory copy still works for this page load.
  }
}

export function saveAuthenticatedSession(token: string, user: AuthenticatedUser): void {
  const previousUser = getAuthenticatedUser();
  if (previousUser && previousUser.id !== user.id && isPosthogConfigured) {
    posthog.reset();
  }

  saveToken(token);
  memoryUser = user;
  restoredIdentity = true;
  try {
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // The in-memory copy still works for this page load.
  }
  identify(user);
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

export function getAuthenticatedUser(): AuthenticatedUser | null {
  try {
    const serialized = sessionStorage.getItem(USER_KEY);
    if (!serialized) return memoryUser;
    const user = JSON.parse(serialized) as AuthenticatedUser;
    return user.id && user.full_name && user.email ? user : null;
  } catch {
    return memoryUser;
  }
}

// App mounts once per page load; restoring here identifies a persisted session
// without repeating identification at every page or event call site.
export function restoreSessionIdentity(): void {
  if (restoredIdentity) return;
  restoredIdentity = true;
  const user = getAuthenticatedUser();
  if (user && getToken()) identify(user);
}

export function clearToken(): void {
  const hadUser = Boolean(getAuthenticatedUser());
  memoryToken = null;
  memoryUser = null;
  restoredIdentity = false;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
  if (hadUser && isPosthogConfigured) posthog.reset();
}
