const TOKEN_KEY = "voiceguard.token";

// The token lives in sessionStorage, so it's gone when the tab closes.
// Storage can be unavailable (e.g. some private-browsing modes), so we keep
// an in-memory copy too and never let storage errors crash the app.
let memoryToken: string | null = null;

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

export function clearToken(): void {
  memoryToken = null;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
}
