// The password-reset link's token (#109) arrives after "#token=" in the page
// address. main.tsx imports this module before anything else, analytics
// included, so it takes the token out of the address before any script can
// record it: PostHog's first page view would otherwise send the full address,
// a live single-use token, to analytics. The reset page then takes the token
// from here.
export const RESET_PATH = "/reset-password";

let heldToken: string | null = null;

// Takes the token from the current address, if it's the reset page's, keeps
// it in memory, and removes it from the address bar and this history entry.
export function holdResetLinkToken(location: Location = window.location, history: History = window.history): void {
  if (location.pathname.replace(/\/+$/, "") !== RESET_PATH || !location.hash) return;
  const token = new URLSearchParams(location.hash.replace(/^#/, "")).get("token")?.trim();
  if (token) heldToken = token;
  history.replaceState(history.state, "", location.pathname + location.search);
}

// The held token, if the page was opened from a reset link. Not cleared on
// reading: React may run the page's setup twice in development, and a used
// token is refused by the server anyway.
export function heldResetLinkToken(): string | null {
  return heldToken;
}

// For tests only.
export function forgetResetLinkToken(): void {
  heldToken = null;
}

holdResetLinkToken();
