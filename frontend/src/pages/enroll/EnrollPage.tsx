import { isAxiosError } from "axios";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { describeEnrollError, getEnrollment, type Enrollment } from "../../api/enroll";
import { endSession } from "../../api/session";
import { SignedInHeader } from "../../components/SignedInHeader";
import { Page } from "../../components/Page";
import type { RecoveringState } from "../RecoverPage";
import { EnrollClosed } from "./EnrollClosed";
import { EnrollDone } from "./EnrollDone";
import { EnrollIntro } from "./EnrollIntro";
import { EnrollRecord } from "./EnrollRecord";
import styles from "../PassagePage.module.css";

type Step = "loading" | "intro" | "record" | "done" | "closed";

// /enroll: the three enrollment steps on one route. Where it starts depends on
// the account: new → intro, part-way → straight back to recording,
// enrolled → done.
export function EnrollPage() {
  const navigate = useNavigate();
  // Came from /recover (#20): finishing replaces the old Voice ID.
  const recovering = (useLocation().state as RecoveringState | null)?.recovering === true;
  const [replaced, setReplaced] = useState(false);
  const [step, setStep] = useState<Step>("loading");
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    getEnrollment()
      .then((status) => {
        if (!current) return;
        setEnrollment(status);
        if (status.status === "enrolled") setStep("done");
        // Only the signup session may record; explain before anyone records.
        else if (status.can_enroll === false) setStep("closed");
        else setStep(status.status === "in_progress" ? "record" : "intro");
      })
      .catch((err) => {
        if (!current) return;
        if (isAxiosError(err) && err.response?.status === 401) {
          endSession();
          navigate("/signin", { replace: true });
          return;
        }
        setError(describeEnrollError(err));
      });
    return () => {
      current = false;
    };
  }, [attempt, navigate]);

  // The session ended on its own (401): forget this tab's note of it.
  function sessionEnded() {
    endSession();
    navigate("/signin", { replace: true });
  }

  function retry() {
    setError("");
    setAttempt((n) => n + 1);
  }

  return (
    <Page>
      <SignedInHeader />
      {step === "loading" &&
        (error ? (
          <div className={styles.problem}>
            <p className={styles.error} role="alert">
              {error}
            </p>
            <button type="button" className={styles.link} onClick={retry}>
              ↻ Try again
            </button>
          </div>
        ) : (
          <p className={styles.status}>Getting your Voice ID ready…</p>
        ))}
      {step === "intro" && <EnrollIntro onStart={() => setStep("record")} />}
      {step === "record" && enrollment && (
        <EnrollRecord
          enrollment={enrollment}
          onChange={setEnrollment}
          onEnrolled={() => {
            // Only a recording finished here replaces anything; opening the
            // page with a Voice ID already in place is the usual done screen.
            setReplaced(recovering);
            setStep("done");
          }}
          onSignedOut={sessionEnded}
          onClosed={() => setStep("closed")}
        />
      )}
      {step === "done" && (
        <EnrollDone
          replaced={replaced}
          // The server ended every session when the new Voice ID replaced the old one.
          onContinue={replaced ? sessionEnded : () => navigate("/verify")}
        />
      )}
      {step === "closed" && <EnrollClosed />}
    </Page>
  );
}
