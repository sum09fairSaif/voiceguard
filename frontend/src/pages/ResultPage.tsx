import { Navigate, useLocation, useNavigate } from "react-router-dom";
import type { VerifyResult } from "../api/verify";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { StepProgress } from "../components/StepProgress";
import styles from "./ResultPage.module.css";

const HEADINGS: Record<VerifyResult["decision"], { eyebrow: string; title: string }> = {
  approved: { eyebrow: "Identity confirmed", title: "You’re in." },
  rejected: { eyebrow: "Not verified", title: "That didn’t match." },
  incomplete: { eyebrow: "Partly verified", title: "Almost there." },
};

const IDENTITY: Record<VerifyResult["identity"], string> = {
  passed: "Matched",
  failed: "Didn’t match",
  not_enrolled: "No voiceprint yet",
};

// A plain result screen so the flow works end to end. #19 (Show the result)
// designs the real one.
export function ResultPage() {
  const navigate = useNavigate();
  const result = (useLocation().state as { result?: VerifyResult } | null)?.result;
  if (!result) {
    // Opened directly, or refreshed: there's nothing to show.
    return <Navigate to="/verify" replace />;
  }

  const { content } = result;
  const heading = HEADINGS[result.decision];

  return (
    <Page>
      <Logo />
      <div className={styles.progress}>
        <StepProgress current={3} total={3} />
      </div>
      <div className={styles.heading}>
        <PageHeading showBadge={false} eyebrow={heading.eyebrow} title={heading.title} subtitle={result.reason} />
      </div>

      <dl className={styles.checks}>
        <div className={styles.row}>
          <dt>Words</dt>
          <dd>
            {content.passed ? "Matched" : "Didn’t match"} ({content.matched}/{content.total} words)
          </dd>
        </div>
        <div className={styles.row}>
          <dt>Voice</dt>
          <dd>{IDENTITY[result.identity]}</dd>
        </div>
        <div className={styles.row}>
          <dt>Liveness</dt>
          <dd>Not checked yet</dd>
        </div>
      </dl>

      <div className={styles.action}>
        <Button type="button" showArrow onClick={() => navigate("/verify", { replace: true })}>
          Try again
        </Button>
      </div>
    </Page>
  );
}
