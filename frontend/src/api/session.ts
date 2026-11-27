import posthog, { isPostHogConfigured } from "../posthog";

// The sign-in token lives in an HttpOnly cookie the API sets (#102): no
// script on the page can read it, so a cross-site scripting bug can't steal
// it. The browser sends it with every request (see client.ts).
//
// What the page keeps is only a note that this tab signed in, and who, so
// screens know where to go without asking the server first, and analytics can
// stay tied to the account. Neither is a secret: the server checks the
// cookie on every request and answers 401 when there's no valid one, and the
// screens then come here to forget the note and send the person to sign in.
const SIGNED_IN_KEY = "voiceguard.signedIn";
const USER_KEY = "voiceguard.user";
// Where the token was kept before #102. Removed on sight, so an old tab
// doesn't leave one behind.
const OLD_TOKEN_KEY = "voiceguard.token";

export type AuthenticatedUser = {
  id: string;
  full_name: string;
  email: string;
  // The keyed stand-in analytics knows this person by (#170). Missing from
  // a sign-in saved before the backend sent it.
  analytics_id?: string;
};

// Storage can be unavailable (e.g. some private-browsing modes), so we keep
// in-memory copies too and never let storage errors crash the app.
let memorySignedIn = false;
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
  // The server's keyed stand-in only, never the account id, email or name.
  if (!isPostHogConfigured || !user.analytics_id) return;
  posthog.identify(user.analytics_id);
}

// After signup or sign-in: the API has set the cookie.
export function startSession(user: AuthenticatedUser): void {
  const previousUser = getStoredUser();
  memorySignedIn = true;
  memoryUser = user;
  try {
    // User first: if the second write then fails, nothing restores a
    // session for the wrong account.
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
    sessionStorage.setItem(SIGNED_IN_KEY, "1");
    sessionStorage.removeItem(OLD_TOKEN_KEY);
  } catch {
    // The in-memory copies still work for this page load.
  }

  if (previousUser && previousUser.id !== user.id && isPostHogConfigured) posthog.reset();
  identify(user);
}

// Whether this tab signed in. A hint for choosing screens, not proof: the
// cookie may have expired, which the next request finds out.
export function isSignedIn(): boolean {
  try {
    return sessionStorage.getItem(SIGNED_IN_KEY) === "1" || memorySignedIn;
  } catch {
    return memorySignedIn;
  }
}

// Call once when the browser starts so a session that survives a page refresh
// remains associated with the same stand-in id.
export function restorePostHogIdentity(): void {
  try {
    sessionStorage.removeItem(OLD_TOKEN_KEY);
  } catch {
    // Nothing stored.
  }
  if (isSignedIn()) {
    const user = getStoredUser();
    if (user) identify(user);
  }
}

// After sign-out, or when the server says the session has ended. Only the
// API can clear the cookie (POST /api/auth/logout); this forgets the note.
export function endSession(): void {
  const hadSession = isSignedIn();
  memorySignedIn = false;
  memoryUser = null;
  try {
    sessionStorage.removeItem(SIGNED_IN_KEY);
    sessionStorage.removeItem(USER_KEY);
    sessionStorage.removeItem(OLD_TOKEN_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
  if (hadSession && isPostHogConfigured) posthog.reset();
}
