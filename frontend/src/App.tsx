import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequireSession } from "./components/RequireSession";
import { SignupPage } from "./pages/SignupPage";
import { VerifyPlaceholderPage } from "./pages/VerifyPlaceholderPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/signup" element={<SignupPage />} />
        <Route
          path="/verify"
          element={
            <RequireSession>
              <VerifyPlaceholderPage />
            </RequireSession>
          }
        />
        {/* "/" and any unknown address start at signup. */}
        <Route path="*" element={<Navigate to="/signup" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
