import { Navigate, useLocation, useNavigate } from "react-router-dom";
import type { VerifyResult } from "../api/verify";
import { SignedInHeader } from "../components/SignedInHeader";
import { useSignOut } from "../hooks/useSignOut";
import { Page } from "../components/Page";
import { ResultView } from "../components/ResultView";
import { describeResult } from "../utils/resultWording";

export function ResultPage() {
  const navigate = useNavigate();
  const signOut = useSignOut();
  const result = (useLocation().state as { result?: VerifyResult } | null)?.result;
  if (!result) {
    // Opened directly, or refreshed: there's nothing to show.
    return <Navigate to="/verify" replace />;
  }

  const view = describeResult(result);

  function handleAction() {
    if (view.action === "home") {
      // The approved check saved a voice-verified token; the account page
      // asks the server, which decides.
      navigate("/account", { replace: true });
      return;
    }
    if (view.action === "retry") {
      // Passages are single-use, so the passage screen fetches a fresh one.
      navigate("/verify", { replace: true });
      return;
    }
    // Done: finish the session (on the server too) and go back to sign in.
    void signOut();
  }

  return (
    <Page>
      <SignedInHeader />
      <ResultView view={view} onAction={handleAction} />
    </Page>
  );
}
