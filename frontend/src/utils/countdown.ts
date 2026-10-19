// The server sends UTC times. If one ever arrives without a timezone, read it
// as UTC rather than the browser's local time.
export function parseServerTime(value: string): number {
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value);
  return Date.parse(hasZone ? value : `${value}Z`);
}

// Whole seconds until expiry, never below zero. An unreadable time counts as
// already expired, so the user is asked for a new passage instead of waiting.
export function secondsLeft(expiresAt: string, now: number = Date.now()): number {
  const remaining = parseServerTime(expiresAt) - now;
  if (Number.isNaN(remaining)) return 0;
  return Math.max(0, Math.ceil(remaining / 1000));
}

export function formatCountdown(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}
