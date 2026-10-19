import { isAxiosError } from "axios";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { describeApiError } from "../api/errors";
import { clearToken } from "../api/session";
import { VERIFY_MESSAGES, submitAttempt } from "../api/verify";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { RecordButton } from "../components/RecordButton";
import { StepProgress } from "../components/StepProgress";
import { useChallenge } from "../hooks/useChallenge";
import { useRecorder } from "../hooks/useRecorder";
import { formatCountdown } from "../utils/countdown";
import { displayPassage } from "../utils/passage";
import styles from "./PassagePage.module.css";

// Statuses where the server refused the upload before using up the passage,
// so the same passage can be read again. After any other failure the passage
// may already be used, so a new one is needed.
const PASSAGE_STILL_VALID = new Set([413, 415, 429]);

export function PassagePage() {
  const navigate = useNavigate();
  const { challenge, loading, error, secondsRemaining, expired, newPhrase } = useChallenge();
  const recorder = useRecorder();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [needsNewPhrase, setNeedsNewPhrase] = useState(false);

  const passageUsable = challenge !== null && !expired && !loading && !needsNewPhrase;

  // A recording only counts for the passage it was read against.
  function handleNewPhrase() {
    recorder.reset();
    setSubmitError("");
    setNeedsNewPhrase(false);
    newPhrase();
  }

  function handleRecordAgain() {
    recorder.reset();
    setSubmitError("");
  }

  async function handleSubmit() {
    if (!challenge || !recorder.recording) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const result = await submitAttempt(recorder.recording, challenge.attempt_id);
      navigate("/result", { state: { result } });
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 401) {
        clearToken();
        navigate("/signup", { replace: true });
        return;
      }
      const status = isAxiosError(err) ? err.response?.status : undefined;
      setNeedsNewPhrase(!(status && PASSAGE_STILL_VALID.has(status)));
      setSubmitError(describeApiError(err, VERIFY_MESSAGES));
      setSubmitting(false);
    }
  }

  const recording = recorder.status === "recording";
  const recorded = recorder.status === "recorded" && recorder.recording !== null;

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
            className={expired || loading || needsNewPhrase ? `${styles.passage} ${styles.faded}` : styles.passage}
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
          {!loading && challenge && !expired && !submitting && (
            <>
              <span className={styles.countdown}>Expires in {formatCountdown(secondsRemaining)}</span>
              <span aria-hidden="true">·</span>
              <button type="button" className={styles.link} onClick={handleNewPhrase} disabled={recording}>
                ↻ New phrase
              </button>
            </>
          )}
          {!loading && challenge && expired && (
            <>
              <span className={styles.countdown}>This phrase has expired.</span>
              <button type="button" className={styles.link} onClick={handleNewPhrase}>
                ↻ Get a new phrase
              </button>
            </>
          )}
          {!loading && !challenge && error && (
            <button type="button" className={styles.link} onClick={handleNewPhrase}>
              ↻ Try again
            </button>
          )}
        </div>
      </section>

      <section className={styles.recorder} aria-label="Record your voice">
        {recorded && !submitError ? (
          <>
            <p className={styles.recorderTitle}>Recording ready</p>
            <p className={styles.recorderHint}>Send it to check your voice, or record it again.</p>
            <div className={styles.actions}>
              <Button type="button" showArrow={!submitting} disabled={submitting || !passageUsable} onClick={handleSubmit}>
                {submitting ? "Checking your voice…" : "Submit"}
              </Button>
              {!submitting && (
                <button type="button" className={styles.link} onClick={handleRecordAgain}>
                  ↻ Record again
                </button>
              )}
            </div>
          </>
        ) : (
          <>
            <RecordButton
              recording={recording}
              disabled={!passageUsable || recorder.status === "requesting" || submitting}
              onClick={recording ? recorder.stop : recorder.start}
            />
            {recording ? (
              <>
                <p className={styles.recorderTitle}>Listening… {formatCountdown(recorder.elapsed)}</p>
                <p className={styles.recorderHint}>Tap to stop when you’ve read the phrase.</p>
              </>
            ) : recorder.status === "requesting" ? (
              <>
                <p className={styles.recorderTitle}>Waiting for your microphone…</p>
                <p className={styles.recorderHint}>Allow microphone access when your browser asks.</p>
              </>
            ) : (
              <>
                <p className={styles.recorderTitle}>Tap to start recording</p>
                <p className={styles.recorderHint}>A few seconds. A little more security.</p>
              </>
            )}
          </>
        )}

        {(recorder.error || submitError) && (
          <div className={styles.problem}>
            <p className={styles.error} role="alert">
              {submitError || recorder.error}
            </p>
            {submitError && needsNewPhrase ? (
              <button type="button" className={styles.link} onClick={handleNewPhrase}>
                ↻ Get a new phrase
              </button>
            ) : (
              <button type="button" className={styles.link} onClick={handleRecordAgain}>
                ↻ Try again
              </button>
            )}
          </div>
        )}
      </section>
    </Page>
  );
}
