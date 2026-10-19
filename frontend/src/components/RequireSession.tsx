import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { getToken } from "../api/session";

// Screens after signup need a token; without one, start again at signup.
export function RequireSession({ children }: { children: ReactNode }) {
  if (!getToken()) {
    return <Navigate to="/signup" replace />;
  }
  return children;
}
