import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequireSession } from "./components/RequireSession";
import { PassagePage } from "./pages/PassagePage";
import { ResultPage } from "./pages/ResultPage";
import { SignupPage } from "./pages/SignupPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/signup" element={<SignupPage />} />
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
        {/* "/" and any unknown address start at signup. */}
        <Route path="*" element={<Navigate to="/signup" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
