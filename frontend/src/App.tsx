import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequireSession } from "./components/RequireSession";
import { PassagePage } from "./pages/PassagePage";
import { ResultPage } from "./pages/ResultPage";
import { SignupPage } from "./pages/SignupPage";

// Development only: Vite sets DEV to false in production builds, so this page
// and its code are left out of what ships.
const DevResultsPage = import.meta.env.DEV ? lazy(() => import("./pages/DevResultsPage")) : null;

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
        {DevResultsPage && (
          <Route
            path="/dev/results"
            element={
              <Suspense>
                <DevResultsPage />
              </Suspense>
            }
          />
        )}
        {/* "/" and any unknown address start at signup. */}
        <Route path="*" element={<Navigate to="/signup" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
