import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequireSession } from "./components/RequireSession";
import { EnrollPage } from "./pages/enroll/EnrollPage";
import { PassagePage } from "./pages/PassagePage";
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
