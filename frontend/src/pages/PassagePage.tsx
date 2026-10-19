import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { StepProgress } from "../components/StepProgress";
import { useChallenge } from "../hooks/useChallenge";
import { formatCountdown } from "../utils/countdown";
import { displayPassage } from "../utils/passage";
import styles from "./PassagePage.module.css";

export function PassagePage() {
  const { challenge, loading, error, secondsRemaining, expired, newPhrase } = useChallenge();

  return (
    <Page>
      <Logo />
      <div className={styles.progress}>
        <StepProgress current={2} total={3} />
      </div>
      <div className={styles.heading}>
        <PageHeading
          showBadge={false}
          eyebrow="Secure sign in"
          title="Just say the word."
          subtitle="Find a quiet spot and read the phrase below in your natural voice."
        />
      </div>

      <section className={styles.card} aria-labelledby="phrase-label">
        <p id="phrase-label" className={styles.cardLabel}>
          Your secure phrase
        </p>

        {challenge ? (
          <p
            className={expired || loading ? `${styles.passage} ${styles.faded}` : styles.passage}
            aria-live="polite"
          >
            “{displayPassage(challenge.passage)}”
          </p>
        ) : error ? (
          <p className={styles.error} role="alert">
            {error}
          </p>
        ) : (
          <p className={styles.status}>Getting your phrase…</p>
        )}

        <div className={styles.footer}>
          {loading && challenge && <span className={styles.status}>Getting a new phrase…</span>}
          {!loading && challenge && !expired && (
            <>
              <span className={styles.countdown}>Expires in {formatCountdown(secondsRemaining)}</span>
              <span aria-hidden="true">·</span>
              <button type="button" className={styles.link} onClick={newPhrase}>
                ↻ New phrase
              </button>
            </>
          )}
          {!loading && challenge && expired && (
            <>
              <span className={styles.countdown}>This phrase has expired.</span>
              <button type="button" className={styles.link} onClick={newPhrase}>
                ↻ Get a new phrase
              </button>
            </>
          )}
          {!loading && !challenge && error && (
            <button type="button" className={styles.link} onClick={newPhrase}>
              ↻ Try again
            </button>
          )}
        </div>
      </section>
    </Page>
  );
}
