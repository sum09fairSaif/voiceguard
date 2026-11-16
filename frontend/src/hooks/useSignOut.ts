import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { logOut } from "../api/auth";
import { clearToken } from "../api/session";

// What the sign-in screen is told when the server couldn't be reached to end
// the session: the device is signed out, but a copied token would still work
// until it expires.
export type SignOutState = { serverSignOutFailed?: boolean };

// Signs out: ends the session on the server, then forgets the token and goes
// to sign in. The token is forgotten even if the server can't be reached, so
// the person is never left signed in on this device; the sign-in screen then
// says the server session ends on its own.
export function useSignOut(): () => Promise<void> {
  const navigate = useNavigate();
  return useCallback(async () => {
    let serverSignOutFailed = false;
    try {
      await logOut();
    } catch {
      serverSignOutFailed = true;
    } finally {
      clearToken();
      const state: SignOutState = { serverSignOutFailed };
      navigate("/signin", { replace: true, state });
    }
  }, [navigate]);
}
