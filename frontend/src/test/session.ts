import { startSession, type AuthenticatedUser } from "../api/session";

export const TEST_USER: AuthenticatedUser = { id: "u1", full_name: "Sam Lee", email: "sam@example.com" };

// As if this tab had signed in: the API would have set the cookie, which
// tests don't need because they never reach a real server.
export function signInForTest(): void {
  startSession(TEST_USER);
}
