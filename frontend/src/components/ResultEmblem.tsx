import checkConfirmed from "../assets/icons/check-confirmed.svg";
import styles from "./ResultEmblem.module.css";

export type EmblemTone = "success" | "failure" | "partial";

// The big circular badge at the top of the result screen (Figma 1:386-1:391).
// Only the success version is in the designs; failure and partial reuse its
// shape in the error and teal colours, with simple icons of our own.
export function ResultEmblem({ tone }: { tone: EmblemTone }) {
  return (
    <div className={`${styles.emblem} ${styles[tone]}`} aria-hidden="true">
      <span className={styles.outer} />
      <span className={styles.middle} />
      <span className={styles.dotLarge} />
      <span className={styles.dotSmall} />
      <span className={styles.core}>
        {tone === "success" && <img src={checkConfirmed} alt="" width={34.0167} height={25.35} />}
        {tone === "failure" && (
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <path d="M6 6L22 22M22 6L6 22" stroke="currentColor" strokeWidth="3.7" strokeLinecap="round" />
          </svg>
        )}
        {tone === "partial" && (
          <svg width="34" height="8" viewBox="0 0 34 8" fill="none">
            <circle cx="4" cy="4" r="3.5" fill="currentColor" />
            <circle cx="17" cy="4" r="3.5" fill="currentColor" />
            <circle cx="30" cy="4" r="3.5" fill="currentColor" />
          </svg>
        )}
      </span>
    </div>
  );
}
