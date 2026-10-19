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
    // Done: there's no home screen in MVP1, so finish the session and start over.
    clearToken();
    navigate("/signup", { replace: true });
  }

  return (
    <Page>
      <Logo />
      <ResultView view={view} onAction={handleAction} />
    </Page>
  );
}
