import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { clearToken } from "../api/session";
import type { VerifyResult } from "../api/verify";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { ResultView } from "../components/ResultView";
import { describeResult } from "../utils/resultWording";

export function ResultPage() {
  const navigate = useNavigate();
  const result = (useLocation().state as { result?: VerifyResult } | null)?.result;
  if (!result) {
    // Opened directly, or refreshed: there's nothing to show.
    return <Navigate to="/verify" replace />;
  }

  const view = describeResult(result);

  function handleAction() {
    if (view.action === "retry") {
      // Passages are single-use, so the passage screen fetches a fresh one.
      navigate("/verify", { replace: true });
      return;
    }
    // Done: there's no home screen yet, so finish the session and go back to sign in.
    clearToken();
    navigate("/signin", { replace: true });
  }

  return (
    <Page>
      <Logo />
      <ResultView view={view} onAction={handleAction} />
    </Page>
  );
}
