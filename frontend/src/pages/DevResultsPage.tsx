import type { VerifyResult } from "../api/verify";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { ResultView } from "../components/ResultView";
import { describeResult } from "../utils/resultWording";

// Development only (never in production builds): every result-screen outcome
// on one page, since a real check can't succeed locally without speech-to-text.
const SAMPLES: { name: string; result: VerifyResult }[] = [
  {
    name: "approved (needs liveness, #17)",
    result: {
      decision: "approved",
      reason: "",
      content: { passed: true, score: 1, matched: 6, total: 6 },
      identity: "passed",
      liveness: "passed",
    },
  },
  {
    name: "incomplete: no voiceprint (most demo accounts)",
    result: {
      decision: "incomplete",
      reason: "",
      content: { passed: true, score: 1, matched: 6, total: 6 },
      identity: "not_enrolled",
      liveness: "not_checked",
    },
  },
  {
    name: "incomplete: voice matched",
    result: {
      decision: "incomplete",
      reason: "",
      content: { passed: true, score: 1, matched: 6, total: 6 },
      identity: "passed",
      liveness: "not_checked",
    },
  },
  {
    name: "rejected: wrong words",
    result: {
      decision: "rejected",
      reason: "",
      content: { passed: false, score: 0.33, matched: 2, total: 6 },
      identity: "not_enrolled",
      liveness: "not_checked",
    },
  },
  {
    name: "rejected: voice didn't match",
    result: {
      decision: "rejected",
      reason: "",
      content: { passed: true, score: 1, matched: 6, total: 6 },
      identity: "failed",
      liveness: "not_checked",
    },
  },
];

export default function DevResultsPage() {
  return (
    <>
      {SAMPLES.map(({ name, result }) => (
        <section key={name} aria-label={name}>
          <p style={{ textAlign: "center", fontSize: 12, padding: "16px 0 0", color: "#697172" }}>{name}</p>
          <Page>
            <Logo />
            <ResultView view={describeResult(result)} onAction={() => {}} />
          </Page>
        </section>
      ))}
    </>
  );
}
