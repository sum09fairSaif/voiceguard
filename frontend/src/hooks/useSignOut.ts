import { isAxiosError } from "axios";
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { logOut } from "../api/auth";
import { endSession } from "../api/session";

// What the sign-in screen is told when the server couldn't be reached to end
// the session. Only the server can clear the sign-in cookie (the page can't
// read or remove it, #102), so the sign-in screen offers to try again.
export type SignOutState = { serverSignOutFailed?: boolean };

// True when the sign-out request did its job: the server ended the session
// and cleared the cookie, or the session had already ended (401, and the
// server clears the cookie then too).
export async function signOutOnServer(): Promise<boolean> {
  try {
    await logOut();
    return true;
  } catch (error) {
    return isAxiosError(error) && error.response?.status === 401;
  }
}

// Signs out: ends the session on the server (which clears the cookie), then
// forgets this tab's note and goes to sign in. If the server can't be
// reached, the sign-in screen says so and offers to try again.
export function useSignOut(): () => Promise<void> {
  const navigate = useNavigate();
  return useCallback(async () => {
    let serverSignOutFailed = false;
    try {
      serverSignOutFailed = !(await signOutOnServer());
    } finally {
      endSession();
      const state: SignOutState = { serverSignOutFailed };
      navigate("/signin", { replace: true, state });
    }
  }, [navigate]);
}
