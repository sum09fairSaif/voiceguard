import { Button } from "../../components/Button";
import { ResultEmblem } from "../../components/ResultEmblem";
// Same layout as the result screen (Figma 1:285 matches 1:369 "Verified").
import styles from "../../components/ResultView.module.css";

// Figma 1:285 "Voice ID ready": step 3 of enrollment. Figma's button says
// "Continue to home"; there's no home screen yet, so it goes to the voice
// check instead, where the new Voice ID can be tried straight away.
export function EnrollDone({ onContinue }: { onContinue: () => void }) {
  return (
    <div className={styles.result}>
      <ResultEmblem tone="success" />
      <p className={`${styles.eyebrow} ${styles.success}`}>Voice ID / 03</p>
      <h1 className={styles.title}>
        One voice.{" "}
        <br />
        All yours.
      </h1>
      <p className={styles.subtitle}>A more personal way to protect what matters to you.</p>

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
          Try your Voice ID
        </Button>
      </div>
    </div>
  );
}
