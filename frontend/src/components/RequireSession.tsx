import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { getToken } from "../api/session";

// Screens after sign-in or signup need a token; without one, go to sign in.
export function RequireSession({ children }: { children: ReactNode }) {
  if (!getToken()) {
    return <Navigate to="/signin" replace />;
  }
  return children;
}
