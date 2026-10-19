export type CheckState = "passed" | "failed" | "pending";

// Small status marks for the result screen's check rows. Not in the designs;
// drawn to match their weight. Colour comes from the surrounding text.
export function CheckStatusIcon({ state }: { state: CheckState }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      {state === "passed" && (
        <path d="M2.5 7.5L5.5 10.5L11.5 3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      )}
      {state === "failed" && (
        <path d="M3.5 3.5L10.5 10.5M10.5 3.5L3.5 10.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      )}
      {state === "pending" && <path d="M3 7H11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />}
    </svg>
  );
}
