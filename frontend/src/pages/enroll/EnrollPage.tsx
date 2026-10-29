import { isAxiosError } from "axios";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { describeEnrollError, getEnrollment, type Enrollment } from "../../api/enroll";
import { clearToken } from "../../api/session";
import { Logo } from "../../components/Logo";
import { Page } from "../../components/Page";
import { EnrollIntro } from "./EnrollIntro";
import { EnrollRecord } from "./EnrollRecord";
import styles from "../PassagePage.module.css";

type Step = "loading" | "intro" | "record" | "done";

// /enroll: the three enrollment steps on one route. Where it starts depends on
// the account: new → intro, part-way → straight back to recording,
// enrolled → done.
export function EnrollPage() {
  const navigate = useNavigate();
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
        setStep(status.status === "enrolled" ? "done" : status.status === "in_progress" ? "record" : "intro");
      })
      .catch((err) => {
        if (!current) return;
        if (isAxiosError(err) && err.response?.status === 401) {
          clearToken();
          navigate("/signin", { replace: true });
          return;
        }
        setError(describeEnrollError(err));
      });
    return () => {
      current = false;
    };
  }, [attempt, navigate]);

  function signOut() {
    clearToken();
    navigate("/signin", { replace: true });
  }

  function retry() {
    setError("");
    setAttempt((n) => n + 1);
  }

  return (
    <Page>
      <Logo />
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
          onEnrolled={() => setStep("done")}
          onSignedOut={signOut}
        />
      )}
      {/* The confirmation screen comes in the next step of this work. */}
      {step === "done" && <p role="status">Your Voice ID is ready.</p>}
    </Page>
  );
}
