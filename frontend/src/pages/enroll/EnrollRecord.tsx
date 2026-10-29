import { isAxiosError } from "axios";
import { useState } from "react";
import { addSample, describeEnrollError, getEnrollment, isAlreadyEnrolled, startOver, type Enrollment } from "../../api/enroll";
import { Button } from "../../components/Button";
import { PageHeading } from "../../components/PageHeading";
import { RecordButton } from "../../components/RecordButton";
import { StepProgress } from "../../components/StepProgress";
import { useRecorder } from "../../hooks/useRecorder";
import { useStillShown } from "../../hooks/useStillShown";
import { formatCountdown } from "../../utils/countdown";
import { displayPassage } from "../../utils/passage";
// Same layout as the passage screen (Figma 1:244 matches 1:327).
import styles from "../PassagePage.module.css";

type Props = {
  enrollment: Enrollment;
  onChange: (enrollment: Enrollment) => void;
  onEnrolled: () => void;
  onSignedOut: () => void;
};

// Figma 1:244 "Record voice": step 2 of enrollment. The user reads a phrase
// and sends it as one sample, until the backend has enough to build the
// voiceprint. Each recording is sent once and not kept.
export function EnrollRecord({ enrollment, onChange, onEnrolled, onSignedOut }: Props) {
  const recorder = useRecorder();
  const [busy, setBusy] = useState<"" | "sending" | "phrase" | "restart">("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  // A reply that arrives after the user has left this screen is ignored.
  const shown = useStillShown();

  const microphoneBusy = recorder.status === "recording" || recorder.status === "requesting";
  const recording = recorder.status === "recording";
  const recorded = recorder.status === "recorded" && recorder.recording !== null;
  const sampleNumber = Math.min(enrollment.samples_accepted + 1, enrollment.samples_required);

  async function run(kind: "sending" | "phrase" | "restart", action: () => Promise<Enrollment>) {
    setBusy(kind);
    setError("");
    try {
      const next = await action();
      if (!shown.current) return;
      if (next.status === "enrolled") {
        onEnrolled();
        return;
      }
      if (kind === "sending") setSaved(`Sample ${next.samples_accepted} saved.`);
      recorder.reset();
      onChange(next);
    } catch (err) {
      if (!shown.current) return;
      if (isAxiosError(err) && err.response?.status === 401) {
        onSignedOut();
        return;
      }
      if (isAlreadyEnrolled(err)) {
        onEnrolled();
        return;
      }
      setError(describeEnrollError(err));
    } finally {
      if (shown.current) setBusy("");
    }
  }

  function handleSend() {
    const audio = recorder.recording;
    if (!audio) return;
    setSaved("");
    void run("sending", () => addSample(audio));
  }

  function handleRecordAgain() {
    recorder.reset();
    setError("");
    setSaved("");
  }

  return (
    <>
      <div className={styles.progress}>
        <StepProgress current={2} total={3} />
      </div>
      <div className={styles.heading}>
        <PageHeading
          showBadge={false}
          eyebrow="Voice ID / 02"
          title="Let’s hear you."
          subtitle="Find a quiet spot and read the phrase below in your natural voice."
        />
      </div>

      <section className={styles.card} aria-labelledby="phrase-label">
        <p id="phrase-label" className={styles.cardLabel}>
          Your secure phrase · Sample {sampleNumber} of {enrollment.samples_required}
        </p>
        <p className={busy === "phrase" ? `${styles.passage} ${styles.faded}` : styles.passage} aria-live="polite">
          “{displayPassage(enrollment.prompt ?? "")}”
        </p>
        <div className={styles.footer}>
          <button
            type="button"
            className={styles.link}
            onClick={() => void run("phrase", getEnrollment)}
            disabled={microphoneBusy || busy !== ""}
          >
            ↻ New phrase
          </button>
          {enrollment.samples_accepted > 0 && (
            <>
              <span aria-hidden="true">·</span>
              <button
                type="button"
                className={styles.link}
                onClick={() => void run("restart", startOver)}
                disabled={microphoneBusy || busy !== ""}
              >
                Start over
              </button>
            </>
          )}
        </div>
      </section>

      <section className={styles.recorder} aria-label="Record your voice">
        {recorded && !error ? (
          <>
            <p className={styles.recorderTitle}>Recording ready</p>
            <p className={styles.recorderHint}>Save it as sample {sampleNumber}, or record it again.</p>
            <div className={styles.actions}>
              <Button type="button" showArrow={busy !== "sending"} disabled={busy !== ""} onClick={handleSend}>
                {busy === "sending" ? "Saving your sample…" : "Save sample"}
              </Button>
              {busy !== "sending" && (
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
              disabled={recorder.status === "requesting" || busy !== ""}
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
                <p className={styles.recorderHint}>{saved || "A few seconds. A little more security."}</p>
              </>
            )}
          </>
        )}

        {(recorder.error || error) && (
          <div className={styles.problem}>
            <p className={styles.error} role="alert">
              {error || recorder.error}
            </p>
            <button type="button" className={styles.link} onClick={handleRecordAgain}>
              ↻ Try again
            </button>
          </div>
        )}
      </section>
    </>
  );
}
