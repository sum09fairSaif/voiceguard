import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { logOut } from "../api/auth";
import { clearToken } from "../api/session";

// Signs out: ends the session on the server, then forgets the token and goes
// to sign in. The token is forgotten even if the server can't be reached, so
// the person is never left signed in on this device.
export function useSignOut(): () => Promise<void> {
  const navigate = useNavigate();
  return useCallback(async () => {
    try {
      await logOut();
    } catch {
      // Offline, already signed out or expired: nothing more to do here.
    } finally {
      clearToken();
      navigate("/signin", { replace: true });
    }
  }, [navigate]);
}
