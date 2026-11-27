import { Button } from "../../components/Button";
import { ResultEmblem } from "../../components/ResultEmblem";
// Same layout as the result screen (Figma 19:287 matches 19:371 "Verified").
import styles from "../../components/ResultView.module.css";

// Figma 19:287 "Voice ID ready": step 3 of enrollment. Figma's button says
// "Continue to home"; there's no home screen yet, so it goes to the voice
// check instead, where the new Voice ID can be tried straight away.
//
// After recording a new Voice ID (#20), every session has ended: the person
// signs in again and passes a voice check with the new voice.
export function EnrollDone({ onContinue, replaced = false }: { onContinue: () => void; replaced?: boolean }) {
  return (
    <div className={styles.result}>
      <ResultEmblem tone="success" />
      <p className={`${styles.eyebrow} ${styles.success}`}>Voice ID / 03</p>
      <h1 className={styles.title}>
        One voice.{" "}
        <br />
        All yours.
      </h1>
      <p className={styles.subtitle}>
        {replaced
          ? "Your new Voice ID replaces the old one. To keep your account safe, you’ve been signed out everywhere: sign in again and use it."
          : "A more personal way to protect what matters to you."}
      </p>

      <ul className={styles.checks} aria-label="Your Voice ID">
        <li className={styles.check}>
          <span className={styles.checkLabel}>Voice ID</span>
          <span className={`${styles.checkStatus} ${styles.passed}`}>Confirmed</span>
        </li>
        <li className={styles.check}>
          <span className={styles.checkLabel}>Protection</span>
          <span className={`${styles.checkStatus} ${styles.passed}`}>Encrypted</span>
        </li>
      </ul>

      <div className={styles.action}>
        <Button type="button" showArrow onClick={onContinue}>
          {replaced ? "Sign in again" : "Try your Voice ID"}
        </Button>
      </div>
    </div>
  );
}
