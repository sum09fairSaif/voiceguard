import type { ResultView as View } from "../utils/resultWording";
import { Button } from "./Button";
import { CheckStatusIcon } from "./CheckStatusIcon";
import { Columns } from "./Page";
import { ResultEmblem } from "./ResultEmblem";
import styles from "./ResultView.module.css";

// The result screen's body (Figma 19:371 "Verified" and our versions of it for
// a failed or partly verified check). One layout for every outcome: only the
// content from describeResult changes.
export function ResultView({ view, onAction }: { view: View; onAction: () => void }) {
  return (
    <Columns
      aside={
        <div className={`${styles.emblem} ${styles.verdict}`}>
          <ResultEmblem tone={view.tone} />
        </div>
      }
    >
      <div className={`${styles.result} ${styles.verdict}`}>
        <p className={`${styles.eyebrow} ${styles[view.tone]}`}>{view.eyebrow}</p>
        <h1 className={styles.title}>{view.title}</h1>
        <p className={styles.subtitle}>{view.subtitle}</p>
        {view.note && <p className={styles.note}>{view.note}</p>}

        {/* Only when the server sent each check's outcome (#112). */}
        {view.checks.length > 0 && (
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
    </Columns>
  );
}
