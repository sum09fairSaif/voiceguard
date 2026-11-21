import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequireSession } from "./components/RequireSession";
import { AccountPage } from "./pages/AccountPage";
import { ConfirmEmailPage } from "./pages/ConfirmEmailPage";
import { EnrollPage } from "./pages/enroll/EnrollPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { PassagePage } from "./pages/PassagePage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { ResultPage } from "./pages/ResultPage";
import { SignInPage } from "./pages/SignInPage";
import { SignupPage } from "./pages/SignupPage";
import { WelcomePage } from "./pages/WelcomePage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WelcomePage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/signup" element={<SignupPage />} />
        {/* No session yet: confirming the email starts it (#111). */}
        <Route path="/confirm-email" element={<ConfirmEmailPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        {/* The emailed link opens this (backend PASSWORD_RESET_URL). */}
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route
          path="/enroll"
          element={
            <RequireSession>
              <EnrollPage />
            </RequireSession>
          }
        />
        <Route
          path="/verify"
          element={
            <RequireSession>
              <PassagePage />
            </RequireSession>
          }
        />
        <Route
          path="/result"
          element={
            <RequireSession>
              <ResultPage />
            </RequireSession>
          }
        />
        <Route
          path="/account"
          element={
            <RequireSession>
              <AccountPage />
            </RequireSession>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
