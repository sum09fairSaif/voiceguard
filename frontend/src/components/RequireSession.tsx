import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { isSignedIn } from "../api/session";

// Screens after sign-in or signup need a session; without one, go to sign
// in. This only checks that this tab signed in: the server checks the cookie
// on every request, and a 401 sends the person back to sign in.
export function RequireSession({ children }: { children: ReactNode }) {
  if (!isSignedIn()) {
    return <Navigate to="/signin" replace />;
  }
  return children;
}
