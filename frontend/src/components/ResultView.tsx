import type { ResultView as View } from "../utils/resultWording";
import { SHOW_CHECK_DETAILS } from "../utils/resultWording";
import { Button } from "./Button";
import { CheckStatusIcon } from "./CheckStatusIcon";
import { ResultEmblem } from "./ResultEmblem";
import styles from "./ResultView.module.css";

// The result screen's body (Figma 1:369 "Verified" and our versions of it for
// a failed or partly verified check). One layout for every outcome: only the
// content from describeResult changes.
export function ResultView({ view, onAction }: { view: View; onAction: () => void }) {
  return (
    <div className={styles.result}>
      <ResultEmblem tone={view.tone} />
      <p className={`${styles.eyebrow} ${styles[view.tone]}`}>{view.eyebrow}</p>
      <h1 className={styles.title}>{view.title}</h1>
      <p className={styles.subtitle}>{view.subtitle}</p>

      {SHOW_CHECK_DETAILS && (
        <ul className={styles.checks} aria-label="Checks">
          {view.checks.map((check) => (
            <li key={check.label} className={styles.check}>
              <span className={styles.checkLabel}>{check.label}</span>
              <span className={`${styles.checkStatus} ${styles[check.state]}`}>
                <CheckStatusIcon state={check.state} />
                {check.detail}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className={styles.action}>
        <Button type="button" showArrow onClick={onAction}>
          {view.actionLabel}
        </Button>
      </div>
    </div>
  );
}
